"""Config flow for the 1KOMMA5° integration."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.exceptions import HomeAssistantError

from .const import CONF_PASSWORD, CONF_SYSTEM_ID, CONF_USERNAME, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


@dataclass
class _SystemEntry:
    """System with pre-fetched title (title requires a blocking API call)."""

    system: Any
    title: str

    def id(self) -> str:
        return self.system.id()


class OneKomma5ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for 1KOMMA5°."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._username: str = ""
        self._password: str = ""
        self._systems: list[_SystemEntry] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step where user enters credentials."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._username = user_input[CONF_USERNAME]
            self._password = user_input[CONF_PASSWORD]

            try:
                # Titles are pre-fetched inside the executor to avoid blocking calls
                self._systems = await self._async_get_systems(self._username, self._password)
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception during login")
                errors["base"] = "unknown"
            else:
                if len(self._systems) == 1:
                    entry = self._systems[0]
                    await self.async_set_unique_id(entry.id())
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=entry.title,
                        data={
                            CONF_USERNAME: self._username,
                            CONF_PASSWORD: self._password,
                            CONF_SYSTEM_ID: entry.id(),
                        },
                    )
                return await self.async_step_system()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_system(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle system selection when the account has multiple systems."""
        if user_input is not None:
            system_id = user_input[CONF_SYSTEM_ID]
            entry = next(e for e in self._systems if e.id() == system_id)
            await self.async_set_unique_id(system_id)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=entry.title,
                data={
                    CONF_USERNAME: self._username,
                    CONF_PASSWORD: self._password,
                    CONF_SYSTEM_ID: system_id,
                },
            )

        system_options = {e.id(): e.title for e in self._systems}
        return self.async_show_form(
            step_id="system",
            data_schema=vol.Schema(
                {vol.Required(CONF_SYSTEM_ID): vol.In(system_options)}
            ),
        )

    async def _async_get_systems(self, username: str, password: str) -> list[_SystemEntry]:
        """Authenticate, fetch systems, and pre-fetch their titles in the executor."""
        from onekommafive.client import Client
        from onekommafive.errors import AuthenticationError, RequestError
        from onekommafive.systems import Systems

        def _fetch() -> list[_SystemEntry]:
            client = Client(username, password)
            systems = Systems(client).get_systems()
            # system.info() makes a blocking HTTP call — must stay in the executor
            return [_SystemEntry(system=s, title=_system_title(s)) for s in systems]

        try:
            return await self.hass.async_add_executor_job(_fetch)
        except AuthenticationError as err:
            raise InvalidAuth from err
        except RequestError as err:
            raise CannotConnect from err


def _system_title(system: Any) -> str:
    """Build a human-readable title. Must be called from the executor thread."""
    info = system.info()
    if info.name:
        return info.name
    if info.address_city:
        return f"1KOMMA5° {info.address_city}"
    return f"1KOMMA5° {system.id()[:8]}"


class CannotConnect(HomeAssistantError):
    """Error raised when the connection to the API fails."""


class InvalidAuth(HomeAssistantError):
    """Error raised when authentication credentials are invalid."""
