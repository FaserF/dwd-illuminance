# Homeassistant DWD Illuminance Sensor
Estimates outdoor illuminance based on current weather conditions and time of day. At night the value is 10. From a little before sunrise to a little after the value is ramped up to whatever the current conditions indicate. The same happens around sunset, except the value is ramped down. Below is an example of what that might look like over a three day period.

<p align="center">
  <img src=images/illuminance_history.png>
</p>

The following sources of weather data are supported:
* [Deutscher Wetterdienst](https://github.com/FL550/dwd_weather)

This Integration is based on https://github.com/pnbruckner/ha-illuminance and only a fork to support DWD (Deutscher Wetter Dienst). If you are using another weather provider, please be sure to use the integration from pnbrucker instead of this one. I will only support DWD, as pnbrucker wont merge my DWD Commits (https://github.com/pnbruckner/ha-illuminance/pull/17). 

You can also have my integration and pnbrucker's integration installed at the same time, as this integration was renamed.


Follow the installation instructions below.
Then add the desired configuration. Here is an example of a typical configuration:
```yaml
sensor:
  - platform: dwd_illuminance
    entity_id: weather.home
```
## Installation
Place a copy of:

[`__init__.py`](custom_components/dwd_illuminance/__init__.py) at `<config>/custom_components/dwd_illuminance/__init__.py`  
[`sensor.py`](custom_components/dwd_illuminance/sensor.py) at `<config>/custom_components/dwd_illuminance/sensor.py`  
[`manifest.json`](custom_components/dwd_illuminance/manifest.json) at `<config>/custom_components/dwd_illuminance/manifest.json`

where `<config>` is your Home Assistant configuration directory.

Or add this github repository to HACS to install it via HACS. 

>__NOTE__: Do not download the file by using the link above directly. Rather, click on it, then on the page that comes up use the `Raw` button.

## Configuration variables
- **entity_id**: Entity ID of entity that indicates current weather conditions. See examples below. Required when not using WU.
- **name** (*Optional*): Name of the sensor. Default is `DWD Illuminance`.
- **scan_interval** (*Optional*): Polling interval.  For non-WU configs only applies during ramp up period around sunrise and ramp down period around sunset. Minimum is 5 minutes. Default is 5 minutes.
## Examples

### Deutscher Wetterdienst
```
sensor:
  - platform: illuminance
    name: DeutscherWetterDienst Illuminance
    entity_id: weather.dwd_weather_home
```