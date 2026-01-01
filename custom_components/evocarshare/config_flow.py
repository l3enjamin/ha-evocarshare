"""Config flow for EvoCarShare integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries, exceptions
from homeassistant.core import HomeAssistant
from homeassistant.helpers import selector

from .const import (
    CONF_RADIUS,
    CONF_SEARCH_MODE,
    CONF_SEARCH_VALUE,
    CONF_TRACKER_ID,
    CONF_ZONE,
    DOMAIN,
    SEARCH_MODE_COUNT,
    SEARCH_MODE_RADIUS,
)
from .helpers import get_zone_by_name, get_zone_config

_LOGGER = logging.getLogger(__name__)


def generate_data_schema(zone_list: list[str]):
    return vol.Schema({
        vol.Required(
            CONF_ZONE,
        ): vol.In(zone_list),
        (CONF_RADIUS): int,
    })


async def validate_config_input(hass: HomeAssistant, data: dict) -> dict[str, Any]:
    """Validate the user input for zone config"""

    if data[CONF_RADIUS] < 0:
        raise InvalidDistance

    zone_data = get_zone_by_name(hass, data[CONF_ZONE])
    if not zone_data:
        raise InvalidZone
    zone_id = zone_data["id"]

    return {CONF_ZONE: zone_id, CONF_RADIUS: data[CONF_RADIUS]}


async def validate_tracker_config_input(hass: HomeAssistant, data: dict) -> dict[str, Any]:
    """Validate the user input for tracker config"""
    if data[CONF_SEARCH_VALUE] <= 0:
        raise InvalidDistance

    return data


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for EvoCarShare."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_PUSH

    async def async_step_user(self, user_input=None):
        """Handle the initial step. Choose between Zone and Device Tracker."""
        return self.async_show_menu(
            step_id="user",
            menu_options=["zone", "tracker"],
        )

    async def async_step_zone(self, user_input=None):
        """Handle the zone step."""
        errors = {}

        if user_input is not None:
            try:
                info = await validate_config_input(self.hass, user_input)
                return self.async_create_entry(title=info[CONF_ZONE], data=info)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidDistance:
                errors["dist"] = "Distance must be > 0"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        zone_list = get_zone_config(self.hass)
        DATA_SCHEMA = generate_data_schema(
            [zone["name"] for zone in zone_list.values()],
        )

        return self.async_show_form(step_id="zone", data_schema=DATA_SCHEMA, errors=errors)

    async def async_step_tracker(self, user_input=None):
        """Handle the tracker step."""
        errors = {}

        if user_input is not None:
            try:
                info = await validate_tracker_config_input(self.hass, user_input)
                title = f"{info[CONF_TRACKER_ID]} ({info[CONF_SEARCH_MODE]})"
                return self.async_create_entry(title=title, data=info)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidDistance:
                errors["dist"] = "Value must be > 0"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        DATA_SCHEMA = vol.Schema({
            vol.Required(CONF_TRACKER_ID): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="device_tracker")
            ),
            vol.Required(CONF_SEARCH_MODE, default=SEARCH_MODE_COUNT): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        {"value": SEARCH_MODE_COUNT, "label": "Closest N Vehicles"},
                        {"value": SEARCH_MODE_RADIUS, "label": "All Vehicles within Distance"},
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(CONF_SEARCH_VALUE, default=5): int,
        })

        return self.async_show_form(step_id="tracker", data_schema=DATA_SCHEMA, errors=errors)


class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidDistance(exceptions.HomeAssistantError):
    """Error to indicate there is an invalid hostname."""


class InvalidZone(exceptions.HomeAssistantError):
    """Error to indicate zone could not be found"""
