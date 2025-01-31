"""Test the Z-Wave JS fan platform."""
import math

import pytest
from voluptuous.error import MultipleInvalid
from zwave_js_server.const import CommandClass
from zwave_js_server.event import Event

from homeassistant.components.fan import (
    ATTR_PERCENTAGE,
    ATTR_PERCENTAGE_STEP,
    ATTR_PRESET_MODE,
    ATTR_PRESET_MODES,
    DOMAIN as FAN_DOMAIN,
    SERVICE_SET_PRESET_MODE,
    SUPPORT_PRESET_MODE,
)
from homeassistant.components.zwave_js.fan import ATTR_FAN_STATE
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_SUPPORTED_FEATURES,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    STATE_UNKNOWN,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry


async def test_generic_fan(hass, client, fan_generic, integration):
    """Test the fan entity for a generic fan that lacks specific speed configuration."""
    node = fan_generic
    entity_id = "fan.generic_fan_controller"
    state = hass.states.get(entity_id)

    assert state
    assert state.state == "off"

    # Test turn on setting speed
    await hass.services.async_call(
        "fan",
        "turn_on",
        {"entity_id": entity_id, "percentage": 66},
        blocking=True,
    )

    assert len(client.async_send_command.call_args_list) == 1
    args = client.async_send_command.call_args[0][0]
    assert args["command"] == "node.set_value"
    assert args["nodeId"] == 17
    assert args["valueId"] == {
        "commandClassName": "Multilevel Switch",
        "commandClass": 38,
        "endpoint": 0,
        "property": "targetValue",
        "propertyName": "targetValue",
        "metadata": {
            "label": "Target value",
            "max": 99,
            "min": 0,
            "type": "number",
            "readable": True,
            "writeable": True,
            "label": "Target value",
        },
    }
    assert args["value"] == 66

    client.async_send_command.reset_mock()

    # Test setting unknown speed
    with pytest.raises(MultipleInvalid):
        await hass.services.async_call(
            "fan",
            "set_percentage",
            {"entity_id": entity_id, "percentage": "bad"},
            blocking=True,
        )

    client.async_send_command.reset_mock()

    # Test turn on no speed
    await hass.services.async_call(
        "fan",
        "turn_on",
        {"entity_id": entity_id},
        blocking=True,
    )

    assert len(client.async_send_command.call_args_list) == 1
    args = client.async_send_command.call_args[0][0]
    assert args["command"] == "node.set_value"
    assert args["nodeId"] == 17
    assert args["valueId"] == {
        "commandClassName": "Multilevel Switch",
        "commandClass": 38,
        "endpoint": 0,
        "property": "targetValue",
        "propertyName": "targetValue",
        "metadata": {
            "label": "Target value",
            "max": 99,
            "min": 0,
            "type": "number",
            "readable": True,
            "writeable": True,
            "label": "Target value",
        },
    }
    assert args["value"] == 255

    client.async_send_command.reset_mock()

    # Test turning off
    await hass.services.async_call(
        "fan",
        "turn_off",
        {"entity_id": entity_id},
        blocking=True,
    )

    assert len(client.async_send_command.call_args_list) == 1
    args = client.async_send_command.call_args[0][0]
    assert args["command"] == "node.set_value"
    assert args["nodeId"] == 17
    assert args["valueId"] == {
        "commandClassName": "Multilevel Switch",
        "commandClass": 38,
        "endpoint": 0,
        "property": "targetValue",
        "propertyName": "targetValue",
        "metadata": {
            "label": "Target value",
            "max": 99,
            "min": 0,
            "type": "number",
            "readable": True,
            "writeable": True,
            "label": "Target value",
        },
    }
    assert args["value"] == 0

    client.async_send_command.reset_mock()

    # Test speed update from value updated event
    event = Event(
        type="value updated",
        data={
            "source": "node",
            "event": "value updated",
            "nodeId": 17,
            "args": {
                "commandClassName": "Multilevel Switch",
                "commandClass": 38,
                "endpoint": 0,
                "property": "currentValue",
                "newValue": 99,
                "prevValue": 0,
                "propertyName": "currentValue",
            },
        },
    )
    node.receive_event(event)

    state = hass.states.get(entity_id)
    assert state.state == "on"
    assert state.attributes[ATTR_PERCENTAGE] == 100

    client.async_send_command.reset_mock()

    event = Event(
        type="value updated",
        data={
            "source": "node",
            "event": "value updated",
            "nodeId": 17,
            "args": {
                "commandClassName": "Multilevel Switch",
                "commandClass": 38,
                "endpoint": 0,
                "property": "currentValue",
                "newValue": 0,
                "prevValue": 0,
                "propertyName": "currentValue",
            },
        },
    )
    node.receive_event(event)

    state = hass.states.get(entity_id)
    assert state.state == "off"
    assert state.attributes[ATTR_PERCENTAGE] == 0


async def test_configurable_speeds_fan(hass, client, hs_fc200, integration):
    """Test a fan entity with configurable speeds."""
    node = hs_fc200
    node_id = 39
    entity_id = "fan.scene_capable_fan_control_switch"

    async def get_zwave_speed_from_percentage(percentage):
        """Set the fan to a particular percentage and get the resulting Zwave speed."""
        client.async_send_command.reset_mock()
        await hass.services.async_call(
            "fan",
            "turn_on",
            {"entity_id": entity_id, "percentage": percentage},
            blocking=True,
        )

        assert len(client.async_send_command.call_args_list) == 1
        args = client.async_send_command.call_args[0][0]
        assert args["command"] == "node.set_value"
        assert args["nodeId"] == node_id
        return args["value"]

    async def get_percentage_from_zwave_speed(zwave_speed):
        """Set the underlying device speed and get the resulting percentage."""
        event = Event(
            type="value updated",
            data={
                "source": "node",
                "event": "value updated",
                "nodeId": node_id,
                "args": {
                    "commandClassName": "Multilevel Switch",
                    "commandClass": 38,
                    "endpoint": 0,
                    "property": "currentValue",
                    "newValue": zwave_speed,
                    "prevValue": 0,
                    "propertyName": "currentValue",
                },
            },
        )
        node.receive_event(event)
        state = hass.states.get(entity_id)
        return state.attributes[ATTR_PERCENTAGE]

    # In 3-speed mode, the speeds are:
    # low = 1-33, med=34-66, high=67-99
    percentages_to_zwave_speeds = [
        [[0], [0]],
        [range(1, 34), range(1, 34)],
        [range(34, 68), range(34, 67)],
        [range(68, 101), range(67, 100)],
    ]

    for percentages, zwave_speeds in percentages_to_zwave_speeds:
        for percentage in percentages:
            actual_zwave_speed = await get_zwave_speed_from_percentage(percentage)
            assert actual_zwave_speed in zwave_speeds
        for zwave_speed in zwave_speeds:
            actual_percentage = await get_percentage_from_zwave_speed(zwave_speed)
            assert actual_percentage in percentages

    state = hass.states.get(entity_id)
    assert math.isclose(state.attributes[ATTR_PERCENTAGE_STEP], 33.3333, rel_tol=1e-3)


async def test_fixed_speeds_fan(hass, client, ge_12730, integration):
    """Test a fan entity with fixed speeds."""
    node = ge_12730
    node_id = 24
    entity_id = "fan.in_wall_smart_fan_control"

    async def get_zwave_speed_from_percentage(percentage):
        """Set the fan to a particular percentage and get the resulting Zwave speed."""
        client.async_send_command.reset_mock()
        await hass.services.async_call(
            "fan",
            "turn_on",
            {"entity_id": entity_id, "percentage": percentage},
            blocking=True,
        )

        assert len(client.async_send_command.call_args_list) == 1
        args = client.async_send_command.call_args[0][0]
        assert args["command"] == "node.set_value"
        assert args["nodeId"] == node_id
        return args["value"]

    async def get_percentage_from_zwave_speed(zwave_speed):
        """Set the underlying device speed and get the resulting percentage."""
        event = Event(
            type="value updated",
            data={
                "source": "node",
                "event": "value updated",
                "nodeId": node_id,
                "args": {
                    "commandClassName": "Multilevel Switch",
                    "commandClass": 38,
                    "endpoint": 0,
                    "property": "currentValue",
                    "newValue": zwave_speed,
                    "prevValue": 0,
                    "propertyName": "currentValue",
                },
            },
        )
        node.receive_event(event)
        state = hass.states.get(entity_id)
        return state.attributes[ATTR_PERCENTAGE]

    # This device has the speeds:
    # low = 1-33, med = 34-67, high = 68-99
    percentages_to_zwave_speeds = [
        [[0], [0]],
        [range(1, 34), range(1, 34)],
        [range(34, 68), range(34, 68)],
        [range(68, 101), range(68, 100)],
    ]

    for percentages, zwave_speeds in percentages_to_zwave_speeds:
        for percentage in percentages:
            actual_zwave_speed = await get_zwave_speed_from_percentage(percentage)
            assert actual_zwave_speed in zwave_speeds
        for zwave_speed in zwave_speeds:
            actual_percentage = await get_percentage_from_zwave_speed(zwave_speed)
            assert actual_percentage in percentages

    state = hass.states.get(entity_id)
    assert math.isclose(state.attributes[ATTR_PERCENTAGE_STEP], 33.3333, rel_tol=1e-3)


async def test_thermostat_fan(hass, client, climate_adc_t3000, integration):
    """Test the fan entity for a z-wave fan."""
    node = climate_adc_t3000
    entity_id = "fan.adc_t3000"

    registry = entity_registry.async_get(hass)
    state = hass.states.get(entity_id)
    assert state is None

    entry = registry.async_get(entity_id)
    assert entry
    assert entry.disabled
    assert entry.disabled_by is entity_registry.RegistryEntryDisabler.INTEGRATION

    # Test enabling entity
    updated_entry = registry.async_update_entity(entity_id, disabled_by=None)
    assert updated_entry != entry
    assert updated_entry.disabled is False

    await hass.config_entries.async_reload(integration.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state
    assert state.state == STATE_ON
    assert state.attributes.get(ATTR_FAN_STATE) == "Idle / off"
    assert state.attributes.get(ATTR_PRESET_MODE) == "Auto low"
    assert state.attributes.get(ATTR_SUPPORTED_FEATURES) == SUPPORT_PRESET_MODE

    # Test setting preset mode
    await hass.services.async_call(
        FAN_DOMAIN,
        SERVICE_SET_PRESET_MODE,
        {ATTR_ENTITY_ID: entity_id, ATTR_PRESET_MODE: "Low"},
        blocking=True,
    )

    assert len(client.async_send_command.call_args_list) == 1
    args = client.async_send_command.call_args[0][0]
    assert args["command"] == "node.set_value"
    assert args["nodeId"] == 68
    assert args["valueId"] == {
        "ccVersion": 3,
        "commandClassName": "Thermostat Fan Mode",
        "commandClass": CommandClass.THERMOSTAT_FAN_MODE.value,
        "endpoint": 0,
        "property": "mode",
        "propertyName": "mode",
        "metadata": {
            "label": "Thermostat fan mode",
            "max": 255,
            "min": 0,
            "type": "number",
            "readable": True,
            "writeable": True,
            "states": {"0": "Auto low", "1": "Low", "6": "Circulation"},
        },
        "value": 0,
    }
    assert args["value"] == 1

    client.async_send_command.reset_mock()

    # Test setting unknown preset mode
    with pytest.raises(ValueError):
        await hass.services.async_call(
            FAN_DOMAIN,
            SERVICE_SET_PRESET_MODE,
            {ATTR_ENTITY_ID: entity_id, ATTR_PRESET_MODE: "Turbo"},
            blocking=True,
        )

    client.async_send_command.reset_mock()

    # Test turning off
    await hass.services.async_call(
        FAN_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )

    assert len(client.async_send_command.call_args_list) == 1
    args = client.async_send_command.call_args[0][0]
    assert args["command"] == "node.set_value"
    assert args["nodeId"] == 68
    assert args["valueId"] == {
        "ccVersion": 3,
        "commandClassName": "Thermostat Fan Mode",
        "commandClass": CommandClass.THERMOSTAT_FAN_MODE.value,
        "endpoint": 0,
        "property": "off",
        "propertyName": "off",
        "metadata": {
            "label": "Thermostat fan turned off",
            "type": "boolean",
            "readable": True,
            "writeable": True,
        },
        "value": False,
    }
    assert args["value"]

    client.async_send_command.reset_mock()

    # Test turning on
    await hass.services.async_call(
        FAN_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )

    assert len(client.async_send_command.call_args_list) == 1
    args = client.async_send_command.call_args[0][0]
    assert args["command"] == "node.set_value"
    assert args["nodeId"] == 68
    assert args["valueId"] == {
        "ccVersion": 3,
        "commandClassName": "Thermostat Fan Mode",
        "commandClass": CommandClass.THERMOSTAT_FAN_MODE.value,
        "endpoint": 0,
        "property": "off",
        "propertyName": "off",
        "metadata": {
            "label": "Thermostat fan turned off",
            "type": "boolean",
            "readable": True,
            "writeable": True,
        },
        "value": False,
    }
    assert not args["value"]

    client.async_send_command.reset_mock()

    # Test fan state update from value updated event
    event = Event(
        type="value updated",
        data={
            "source": "node",
            "event": "value updated",
            "nodeId": 68,
            "args": {
                "commandClassName": "Thermostat Fan State",
                "commandClass": CommandClass.THERMOSTAT_FAN_STATE.value,
                "endpoint": 0,
                "property": "state",
                "newValue": 4,
                "prevValue": 0,
                "propertyName": "state",
            },
        },
    )
    node.receive_event(event)

    state = hass.states.get(entity_id)
    assert state.attributes.get(ATTR_FAN_STATE) == "Circulation mode"

    client.async_send_command.reset_mock()

    # Test unknown fan state update from value updated event
    event = Event(
        type="value updated",
        data={
            "source": "node",
            "event": "value updated",
            "nodeId": 68,
            "args": {
                "commandClassName": "Thermostat Fan State",
                "commandClass": CommandClass.THERMOSTAT_FAN_STATE.value,
                "endpoint": 0,
                "property": "state",
                "newValue": 99,
                "prevValue": 0,
                "propertyName": "state",
            },
        },
    )
    node.receive_event(event)

    state = hass.states.get(entity_id)
    assert not state.attributes.get(ATTR_FAN_STATE)

    client.async_send_command.reset_mock()

    # Test fan mode update from value updated event
    event = Event(
        type="value updated",
        data={
            "source": "node",
            "event": "value updated",
            "nodeId": 68,
            "args": {
                "commandClassName": "Thermostat Fan Mode",
                "commandClass": CommandClass.THERMOSTAT_FAN_MODE.value,
                "endpoint": 0,
                "property": "mode",
                "newValue": 1,
                "prevValue": 0,
                "propertyName": "mode",
            },
        },
    )
    node.receive_event(event)

    state = hass.states.get(entity_id)
    assert state.attributes.get(ATTR_PRESET_MODE) == "Low"

    client.async_send_command.reset_mock()

    # Test fan mode update from value updated event for an unknown mode
    event = Event(
        type="value updated",
        data={
            "source": "node",
            "event": "value updated",
            "nodeId": 68,
            "args": {
                "commandClassName": "Thermostat Fan Mode",
                "commandClass": CommandClass.THERMOSTAT_FAN_MODE.value,
                "endpoint": 0,
                "property": "mode",
                "newValue": 79,
                "prevValue": 0,
                "propertyName": "mode",
            },
        },
    )
    node.receive_event(event)

    state = hass.states.get(entity_id)
    assert not state.attributes.get(ATTR_PRESET_MODE)

    client.async_send_command.reset_mock()

    # Test fan mode turned off update from value updated event
    event = Event(
        type="value updated",
        data={
            "source": "node",
            "event": "value updated",
            "nodeId": 68,
            "args": {
                "commandClassName": "Thermostat Fan Mode",
                "commandClass": CommandClass.THERMOSTAT_FAN_MODE.value,
                "endpoint": 0,
                "property": "off",
                "newValue": True,
                "prevValue": False,
                "propertyName": "off",
            },
        },
    )
    node.receive_event(event)

    state = hass.states.get(entity_id)
    assert state.state == STATE_OFF


async def test_thermostat_fan_without_off(
    hass, client, climate_radio_thermostat_ct100_plus, integration
):
    """Test the fan entity for a z-wave fan without "off" property."""
    entity_id = "fan.z_wave_thermostat"

    registry = entity_registry.async_get(hass)
    state = hass.states.get(entity_id)
    assert state is None

    entry = registry.async_get(entity_id)
    assert entry
    assert entry.disabled
    assert entry.disabled_by is entity_registry.RegistryEntryDisabler.INTEGRATION

    # Test enabling entity
    updated_entry = registry.async_update_entity(entity_id, disabled_by=None)
    assert updated_entry != entry
    assert updated_entry.disabled is False

    await hass.config_entries.async_reload(integration.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state
    assert state.state == STATE_UNKNOWN

    # Test turning off
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            FAN_DOMAIN,
            SERVICE_TURN_OFF,
            {ATTR_ENTITY_ID: entity_id},
            blocking=True,
        )

    assert len(client.async_send_command.call_args_list) == 0
    assert state.state == STATE_UNKNOWN

    client.async_send_command.reset_mock()

    # Test turning on
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            FAN_DOMAIN,
            SERVICE_TURN_ON,
            {ATTR_ENTITY_ID: entity_id},
            blocking=True,
        )

    assert len(client.async_send_command.call_args_list) == 0
    assert state.state == STATE_UNKNOWN

    client.async_send_command.reset_mock()


async def test_thermostat_fan_without_preset_modes(
    hass, client, climate_adc_t3000_missing_fan_mode_states, integration
):
    """Test the fan entity for a z-wave fan without "states" metadata."""
    entity_id = "fan.adc_t3000_missing_fan_mode_states"

    registry = entity_registry.async_get(hass)
    state = hass.states.get(entity_id)
    assert state is None

    entry = registry.async_get(entity_id)
    assert entry
    assert entry.disabled
    assert entry.disabled_by is entity_registry.RegistryEntryDisabler.INTEGRATION

    # Test enabling entity
    updated_entry = registry.async_update_entity(entity_id, disabled_by=None)
    assert updated_entry != entry
    assert updated_entry.disabled is False

    await hass.config_entries.async_reload(integration.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state

    assert not state.attributes.get(ATTR_PRESET_MODE)
    assert not state.attributes.get(ATTR_PRESET_MODES)
