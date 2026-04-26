"""Config flow for the 1KOMMA5° integration."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError

from .const import (
    CONF_FEED_IN_TARIFF,
    CONF_PASSWORD,
    CONF_SYSTEM_ID,
    CONF_USERNAME,
    DEFAULT_FEED_IN_TARIFF,
    DOMAIN,
)

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

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: Any) -> "OneKomma5OptionsFlow":
        """Return the options flow handler."""
        return OneKomma5OptionsFlow(config_entry)

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

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle re-authentication when credentials become invalid."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show form for new credentials and update the entry."""
        return await self._async_credentials_step(
            entry=self._get_reauth_entry(),
            step_id="reauth_confirm",
            user_input=user_input,
            log_label="reauth",
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Allow the user to update credentials proactively."""
        return await self._async_credentials_step(
            entry=self._get_reconfigure_entry(),
            step_id="reconfigure",
            user_input=user_input,
            log_label="reconfigure",
        )

    async def _async_credentials_step(
        self,
        entry: Any,
        step_id: str,
        user_input: dict[str, Any] | None,
        log_label: str,
    ) -> ConfigFlowResult:
        """Shared form handler for reauth and reconfigure flows.

        Both flows present the same credential form, validate against the
        existing system_id and call ``async_update_reload_and_abort`` on
        success.  Only the step_id, the log label and which entry-getter
        produced ``entry`` differ between them.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                systems = await self._async_get_systems(
                    user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
                )
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception during %s", log_label)
                errors["base"] = "unknown"
            else:
                existing_system_id = entry.data[CONF_SYSTEM_ID]
                if not any(s.id() == existing_system_id for s in systems):
                    errors["base"] = "system_not_found"
                else:
                    return self.async_update_reload_and_abort(
                        entry,
                        data_updates={
                            CONF_USERNAME: user_input[CONF_USERNAME],
                            CONF_PASSWORD: user_input[CONF_PASSWORD],
                        },
                    )

        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_USERNAME, default=entry.data[CONF_USERNAME]
                    ): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
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


class OneKomma5OptionsFlow(OptionsFlow):
    """Handle options for the 1KOMMA5° integration."""

    def __init__(self, config_entry: Any) -> None:
        """Store the config entry for use in the options steps."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the options form."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current_tariff = self._config_entry.options.get(CONF_FEED_IN_TARIFF, DEFAULT_FEED_IN_TARIFF)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_FEED_IN_TARIFF, default=current_tariff): vol.All(
                        vol.Coerce(float), vol.Range(min=0.0, max=0.5)
                    ),
                }
            ),
        )


class CannotConnect(HomeAssistantError):
    """Error raised when the connection to the API fails."""


class InvalidAuth(HomeAssistantError):
    """Error raised when authentication credentials are invalid."""
