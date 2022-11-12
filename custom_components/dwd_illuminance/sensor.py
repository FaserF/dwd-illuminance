"""
Illuminance Sensor. 

A Sensor platform that estimates outdoor illuminance from current weather conditions.
"""
import asyncio
import datetime as dt
import logging
from math import asin, cos, exp, radians, sin

import aiohttp
import async_timeout
import voluptuous as vol

from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN, PLATFORM_SCHEMA
try:
    from custom_components.dwd_weather.weather import ATTRIBUTION as DWD_ATTRIBUTION
except:
    DWD_ATTRIBUTION = "no_dwd"
from homeassistant.const import (
    ATTR_ATTRIBUTION,
    CONF_ENTITY_ID,
    EVENT_CORE_CONFIG_UPDATE,
    LIGHT_LUX,
)
from .const import (
    CONF_MODE,
    CONF_NAME,
    CONF_SCAN_INTERVAL,

    DOMAIN,
)
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.sun import get_astral_location
import homeassistant.util.dt as dt_util

DEFAULT_NAME = 'DWD Illuminance'
MIN_SCAN_INTERVAL = dt.timedelta(minutes=5)
DEFAULT_SCAN_INTERVAL = dt.timedelta(minutes=5)

DWD_MAPPING = (
    (10, ('lightning', 'lightning-rainy', 'pouring')),
    (5, ('cloudy', 'fog', 'rainy', 'snowy', 'snowy-rainy', 'windy')),
    (3, ('mostlycloudy', )),
    (2, ('partlycloudy', )),
    (1, ('sunny', 'clear-night')),
)

_LOGGER = logging.getLogger(__name__)

MODE_NORMAL = "normal"
MODE_SIMPLE = "simple"
MODES = (MODE_NORMAL, MODE_SIMPLE)

_20_MIN = dt.timedelta(minutes=20)
_40_MIN = dt.timedelta(minutes=40)

async def async_setup_entry(
    hass, entry, async_add_entities, discovery_info=None
):
    """Setup sensors from a config entry created in the integrations UI."""
    config = hass.data[DOMAIN][entry.entry_id]
    def get_loc_elev(event=None):
        """Get HA Location object & elevation."""
        try:
            loc, elev = get_astral_location(hass)
        except TypeError:
            loc = get_astral_location(hass)
            elev = None
        hass.data["illuminance"] = loc, elev

    if "illuminance" not in hass.data:
        get_loc_elev()
        hass.bus.async_listen(EVENT_CORE_CONFIG_UPDATE, get_loc_elev)
    _LOGGER.debug("Sensor async_setup_entry")
    if entry.options:
        config.update(entry.options)
    sensors = IlluminanceSensor(config, entry)
    async_add_entities(sensors, update_before_add=True)
    async_add_entities(
        [
            IlluminanceSensor(config, entry)
        ],
        update_before_add=True
    )


def _illumiance(elev):
    """Calculate illuminance from sun at given elevation."""
    elev_rad = radians(elev)
    u = sin(elev_rad)
    x = 753.66156
    s = asin(x * cos(elev_rad) / (x + 1))
    m = x * (cos(s) - u) + cos(s)
    m = exp(-0.2 * m) * u + 0.0289 * exp(-0.042 * m) * (
        1 + (elev + 90) * u / 57.29577951
    )
    return 133775 * m


class IlluminanceSensor(Entity):
    """Illuminance sensor."""

    def __init__(self, config, entry):
        """Initialize."""
        self._entity_id = entry.entry_id
        self._name = f"DWD illuminance {entry.entry_id}"#config[CONF_NAME]
        self._mode = config[CONF_MODE]
        if self._mode == MODE_SIMPLE:
            self._sun_data = None
        self._state = None
        self._unsub = None
        self._sk_mapping = None
        self._cd_mapping = None

    async def async_added_to_hass(self):
        """Run when entity about to be added to hass."""

        def get_mappings(state):
            #if not state:
            #    if self.hass.is_running:
            #        _LOGGER.error("%s: State not found: %s", self.name, self._entity_id)
            #    return False
            attribution = state.attributes.get(ATTR_ATTRIBUTION)
            if not attribution:
                _LOGGER.error(
                    "%s: No %s attribute: %s",
                    self.name,
                    ATTR_ATTRIBUTION,
                    self._entity_id,
                )
                return False

            if attribution == DWD_ATTRIBUTION:
                self._sk_mapping = DWD_MAPPING
            else:
                _LOGGER.error(
                    "%s: Only DWD is supported! Unsupported sensor: %s, attribution: %s",
                    self.name,
                    self._entity_id,
                    attribution,
                )
                return False

            _LOGGER.info("%s: Supported attribution: %s", self.name, attribution)
            return True

        if not get_mappings(self.hass.states.get(self._entity_id)):
            _LOGGER.info("%s: Waiting for %s", self.name, self._entity_id)

        @callback
        def sensor_state_listener(event):
            new_state = event.data["new_state"]
            old_state = event.data["old_state"]
            if not self._sk_mapping:
                if not get_mappings(new_state):
                    return
            if new_state and (not old_state or new_state.state != old_state.state):
                self.async_schedule_update_ha_state(True)

        # Update whenever source entity changes.
        self._unsub = async_track_state_change_event(
            self.hass, self._entity_id, sensor_state_listener
        )

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity will be removed from hass."""
        if self._unsub:
            self._unsub()
            self._unsub = None

    @property
    def name(self):
        """Return name."""
        return self._name

    @property
    def state(self):
        """Return state."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return unit of measurement."""
        return LIGHT_LUX

    async def async_update(self):
        """Update state."""
        if not self._sk_mapping:
            return

        _LOGGER.debug("Updating %s", self.name)

        now = dt_util.now().replace(microsecond=0)

        if self._mode == MODE_SIMPLE:
            sun_factor = self._sun_factor(now)

            # No point in getting conditions because estimated illuminance derived
            # from it will just be multiplied by zero. I.e., it's nighttime.
            if sun_factor == 0:
                self._state = 10
                return

        state = self.hass.states.get(self._entity_id)
        if state is None:
            if self.hass.is_running:
                _LOGGER.error("%s: State not found: %s", self.name, self._entity_id)
            return

        raw_conditions = state.state
        if self._cd_mapping:
            conditions = self._cd_mapping.get(raw_conditions)
        else:
            conditions = raw_conditions

        sk = None
        for _sk, _conditions in self._sk_mapping:
            if conditions in _conditions:
                sk = _sk
                break
        if not sk:
            if self.hass.is_running:
                _LOGGER.error(
                    "%s: Unexpected current observation: %s", self.name, raw_conditions
                )
            return

        if self._mode == MODE_SIMPLE:
            illuminance = 10000 * sun_factor
        else:
            illuminance = _illumiance(self._astral_event("solar_elevation", now))
        self._state = round(illuminance / sk)

    def _astral_event(self, event, date_or_dt):
        loc, elev = self.hass.data["illuminance"]
        if elev is None:
            return getattr(loc, event)(date_or_dt)
        return getattr(loc, event)(date_or_dt, observer_elevation=elev)

    def _sun_factor(self, now):
        now_date = now.date()

        if self._sun_data and self._sun_data[0] == now_date:
            (sunrise_begin, sunrise_end, sunset_begin, sunset_end) = self._sun_data[1]
        else:
            sunrise = self._astral_event("sunrise", now_date)
            sunset = self._astral_event("sunset", now_date)
            sunrise_begin = sunrise - _20_MIN
            sunrise_end = sunrise + _40_MIN
            sunset_begin = sunset - _40_MIN
            sunset_end = sunset + _20_MIN
            self._sun_data = (
                now_date,
                (sunrise_begin, sunrise_end, sunset_begin, sunset_end),
            )

        if sunrise_end < now < sunset_begin:
            # Daytime
            return 1
        if now < sunrise_begin or sunset_end < now:
            # Nighttime
            return 0
        if now <= sunrise_end:
            # Sunrise
            return (now - sunrise_begin).total_seconds() / (60 * 60)
        # Sunset
        return (sunset_end - now).total_seconds() / (60 * 60)