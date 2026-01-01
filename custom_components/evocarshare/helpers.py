from base64 import b64decode, b64encode
from zlib import compress, decompress

from homeassistant.core import HomeAssistant

from evocarshare import GpsCoord

from .const import CONF_TRACKER_ID, CONF_ZONE, LATITUDE, LONGITUDE


def get_zone_config(hass: HomeAssistant):
    zones = {}

    # Create and append a default 'Home' zone.
    zones["home"] = {
        "id": "home",
        "name": hass.config.location_name,
        LATITUDE: hass.config.latitude,
        LONGITUDE: hass.config.longitude,
    }

    return zones | hass.data["zone"].data


def get_zone_by_name(hass: HomeAssistant, name: str):
    for v in get_zone_config(hass).values():
        if v["name"] == name:
            return v
    raise KeyError(name)


def get_location(hass: HomeAssistant, config_data: dict) -> GpsCoord | None:
    """Return GpsCoord for a given config data (zone or tracker)."""
    if CONF_ZONE in config_data:
        zone_id = config_data[CONF_ZONE]
        target_zone = get_zone_config(hass)[zone_id]
        return GpsCoord(
            target_zone[LATITUDE],
            target_zone[LONGITUDE],
        )
    elif CONF_TRACKER_ID in config_data:
        tracker_id = config_data[CONF_TRACKER_ID]
        state = hass.states.get(tracker_id)
        if state is None:
            return None
        lat = state.attributes.get(LATITUDE)
        lon = state.attributes.get(LONGITUDE)
        if lat is None or lon is None:
            return None
        return GpsCoord(lat, lon)
    return None


def obscure(s: str) -> str:
    return b64encode(compress(bytes(s, "utf8")))


def deobscure(s: str) -> str:
    return decompress(b64decode(s)).decode("utf-8")
