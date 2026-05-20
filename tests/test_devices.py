"""Tests for the parsing of a decrypted telemetry packet into device attributes.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

import asyncio
import logging
import os
from typing import Any
from unittest import mock

import pytest

from SolixBLE import (
    C300,
    C300DC,
    C800,
    C1000,
    C1000G2,
    ChargingStatus,
    LightStatus,
    PortOverload,
    PortStatus,
    PrimeCharger160w,
    PrimeDevice,
    Solarbank2,
    SolixBLEDevice,
    TemperatureUnit,
)
from SolixBLE.devices.solarbank2 import (
    ENV_SB2_ANKER_USER_ID,
    MaxLoadSB2,
    Solarbank2Prime,
    Solarbank2Common,
)
from SolixBLE.states import GridStatus, LightMode, SBPowerCutoff, SBUsageMode
from tests.const import (
    MOCK_BLE_DEVICE,
    NEGOTIATION_RESPONSES_PRIME,
    NEGOTIATION_RESPONSES_SOLIX,
)
from tests.helpers import MockDevice


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "device_class,payload,mapping",
    [
        # The C800(X) uses the same mappings as the C1000(X) minus the expansion
        # battery stuff. This uses the test data for the C1000(X) as I do not
        # have data for a C800(X).
        pytest.param(
            C800,
            "a10131a2050300000000a3050300000000a403026b06a503020000a603020000a703020000a803020000a903020000aa03020000ab03020000ac03020000ad03020000ae03020000af03020000b003020100b103020000b203020000b30302a600b403020000b503020000b60302ff01b703020000b803029a00b903020000ba0302a600bb03020000bc020100bd020117be020100bf020101c0020100c1020157c2020100c3020164c4020100c5020100c6020100c7020100c8020100c9020100ca020100cb020100cc020100cd020100ce020100cf020100d0110041504339464530453237333030323735e5020100",
            {
                "ac_timer_remaining": 0,
                "ac_timer": None,
                "hours_remaining": 20.3,
                "days_remaining": 6,
                "ac_power_in": 0,
                "ac_power_out": 0,
                "usb_c1_power": 0,
                "usb_c2_power": 0,
                "usb_a1_power": 0,
                "usb_a2_power": 0,
                "solar_power_in": 0,
                "power_in": 0,
                "power_out": 1,
                "software_version": "1.6.6",
                "ac_output": PortStatus.NOT_CONNECTED,
                # "solar_port": PortStatus.NOT_CONNECTED,
                "temperature": 23,
                "battery_percentage": 87,
                "battery_health": 100,
                "serial_number": "APC9FE0E27300275",
            },
            id="c800_basic",
        ),
        pytest.param(
            C1000,
            "a10131a2050300000000a3050300000000a403026b06a503020000a603020000a703020000a803020000a903020000aa03020000ab03020000ac03020000ad03020000ae03020000af03020000b003020100b103020000b203020000b30302a600b403020000b503020000b60302ff01b703020000b803029a00b903020000ba0302a600bb03020000bc020100bd020117be020100bf020101c0020100c1020157c2020100c3020164c4020100c5020100c6020100c7020100c8020100c9020100ca020100cb020100cc020100cd020100ce020100cf020100d0110041504339464530453237333030323735e5020100",
            {
                "ac_timer_remaining": 0,
                "ac_timer": None,
                "hours_remaining": 20.3,
                "days_remaining": 6,
                "ac_power_in": 0,
                "ac_power_out": 0,
                "usb_c1_power": 0,
                "usb_c2_power": 0,
                "usb_a1_power": 0,
                "usb_a2_power": 0,
                "solar_power_in": 0,
                "power_in": 0,
                "power_out": 1,
                "software_version": "1.6.6",
                "software_version_expansion": "0",
                "software_version_controller": "1.6.6",
                "ac_output": PortStatus.NOT_CONNECTED,
                # "solar_port": PortStatus.NOT_CONNECTED,
                "temperature": 23,
                "temperature_expansion": 0,
                "battery_percentage": 87,
                "battery_percentage_expansion": 0,
                "battery_health": 100,
                "battery_health_expansion": 0,
                "num_expansion": 0,
                "serial_number": "APC9FE0E27300275",
            },
            id="c1000_idle",
        ),
        pytest.param(
            C1000,
            "a10131a2050300000000a3050300000000a403020800a503020000a60302d203a703020000a803020000a903020000aa03020000ab03020000ac03020000ad03020000ae03020000af03020000b00302d303b103020000b203020000b30302a600b403020000b50302ff01b60302ff01b703020000b803029a00b903020000ba0302a600bb03020100bc020100bd02011abe020100bf020101c0020100c102014fc2020100c3020164c4020100c5020100c6020100c7020100c8020100c9020100ca020100cb020100cc020100cd020100ce020100cf020100d0110041504339464530453237333030323735e5020100",
            {
                "ac_timer_remaining": 0,
                "ac_timer": None,
                "hours_remaining": 0.8,
                "days_remaining": 0,
                "ac_power_in": 0,
                "ac_power_out": 978,
                "usb_c1_power": 0,
                "usb_c2_power": 0,
                "usb_a1_power": 0,
                "usb_a2_power": 0,
                "solar_power_in": 0,
                "power_in": 0,
                "power_out": 979,
                "software_version": "1.6.6",
                "software_version_expansion": "0",
                "software_version_controller": "1.6.6",
                "ac_output": PortStatus.OUTPUT,
                # "solar_port": PortStatus.NOT_CONNECTED,
                "temperature": 26,
                "temperature_expansion": 0,
                "battery_percentage": 79,
                "battery_percentage_expansion": 0,
                "battery_health": 100,
                "battery_health_expansion": 0,
                "num_expansion": 0,
                "serial_number": "APC9FE0E27300275",
            },
            id="c1000_ac_load",
        ),
        pytest.param(
            C1000,
            "a10131a2050300000000a3050300000000a403020f00a503024802a603020000a703020000a803020000a903020000aa03020000ab03020000ac03020000ad03020000ae03020000af03024802b003020000b103020000b203020100b30302a600b403020000b50302ff01b60302ff01b703020000b803029a00b903020000ba0302a600bb03020000bc020102bd020117be020100bf020102c0020100c1020118c2020100c3020164c4020100c5020100c6020100c7020100c8020100c9020100ca020100cb020100cc020100cd020100ce020100cf020100d0110041504339464530453237333030323735e5020100",
            {
                "ac_timer_remaining": 0,
                "ac_timer": None,
                "hours_remaining": 1.5,
                "days_remaining": 0,
                "ac_power_in": 584,
                "ac_power_out": 0,
                "usb_c1_power": 0,
                "usb_c2_power": 0,
                "usb_a1_power": 0,
                "usb_a2_power": 0,
                "solar_power_in": 0,
                "power_in": 584,
                "power_out": 0,
                "software_version": "1.6.6",
                "software_version_expansion": "0",
                "software_version_controller": "1.6.6",
                "ac_output": PortStatus.NOT_CONNECTED,
                # "solar_port": PortStatus.NOT_CONNECTED,
                "temperature": 23,
                "temperature_expansion": 0,
                "battery_percentage": 24,
                "battery_percentage_expansion": 0,
                "battery_health": 100,
                "battery_health_expansion": 0,
                "num_expansion": 0,
                "serial_number": "APC9FE0E27300275",
            },
            id="c1000_ac_charge",
        ),
        pytest.param(
            C1000,
            "a10131a2050300000000a3050300000000a403025a00a503020000a603020000a703020000a803020000a903020000aa03020000ab03020000ac03020000ad03020000ae03026200af03026200b003020300b103020000b203020000b30302a600b403020000b503020000b60302ff01b703020000b803029a00b903020000ba0302a600bb03020000bc020101bd020117be020100bf020102c0020100c102011ac2020100c3020164c4020100c5020100c6020100c7020100c8020100c9020100ca020100cb020100cc020100cd020100ce020100cf020100d0110041504339464530453237333030323735e5020100",
            {
                "ac_timer_remaining": 0,
                "ac_timer": None,
                "hours_remaining": 9.0,
                "days_remaining": 0,
                "ac_power_in": 0,
                "ac_power_out": 0,
                "usb_c1_power": 0,
                "usb_c2_power": 0,
                "usb_a1_power": 0,
                "usb_a2_power": 0,
                "solar_power_in": 98,
                "power_in": 98,
                "power_out": 3,
                "software_version": "1.6.6",
                "software_version_expansion": "0",
                "software_version_controller": "1.6.6",
                "ac_output": PortStatus.NOT_CONNECTED,
                # "solar_port": PortStatus.INPUT,
                "temperature": 23,
                "temperature_expansion": 0,
                "battery_percentage": 26,
                "battery_percentage_expansion": 0,
                "battery_health": 100,
                "battery_health_expansion": 0,
                "num_expansion": 0,
                "serial_number": "APC9FE0E27300275",
            },
            id="c1000_dc_charge_light_high",
        ),
        pytest.param(
            C1000,
            "a10131a2050300000000a3050300000000a403022900a503020000a603020000a703021400a803021000a903020b00aa03020100ab03020000ac03020000ad03020000ae03020000af03020000b003023100b103020000b203020000b30302a600b403020000b503020000b60302ff01b703020000b803029a00b903020000ba0302a600bb03020000bc020100bd020117be020100bf020101c0020100c1020117c2020100c3020164c4020100c5020100c6020101c7020101c8020101c9020101ca020100cb020100cc020100cd020100ce020100cf020100d0110041504339464530453237333030323735e5020100",
            {
                "ac_timer_remaining": 0,
                "ac_timer": None,
                "hours_remaining": 4.1,
                "days_remaining": 0,
                "ac_power_in": 0,
                "ac_power_out": 0,
                "usb_c1_power": 20,
                "usb_c2_power": 16,
                "usb_a1_power": 11,
                "usb_a2_power": 1,
                "solar_power_in": 0,
                "power_in": 0,
                "power_out": 49,
                "software_version": "1.6.6",
                "software_version_expansion": "0",
                "software_version_controller": "1.6.6",
                "ac_output": PortStatus.NOT_CONNECTED,
                # "solar_port": PortStatus.NOT_CONNECTED,
                "temperature": 23,
                "temperature_expansion": 0,
                "battery_percentage": 23,
                "battery_percentage_expansion": 0,
                "battery_health": 100,
                "battery_health_expansion": 0,
                "num_expansion": 0,
                "serial_number": "APC9FE0E27300275",
            },
            id="c1000_usb_load",
        ),
        pytest.param(
            C1000G2,
            "a10134a221062011415043444b39363146333734303032393000054131373633060201010100a30b0400000000b0040058dc00a41b0400000000b0043201000000000000001e00010000000000640103a506041700646400a60a04000000000000ab2a64a70704000000010000a80404000000aa0404000000ab0404000000ac0404000000ae0404000000b20404000000d91a0400001964010000000100000000000000000000000000000000da18040000000000000000000001e00164057f00000000000000dc06040000000000f91d0406020101050005000000000005000500050300010000000000020200fa150401010101001f0300000000000000000000000000fd0e0031373634363538323735393838fe0503638c2e69f0",
            {
                "serial_number": "APCDK961F37400290",
                "part_number": "A1763",
                "temperature": 23,
                "battery_percentage": 100,
                "battery_health": 100,
                "power_out": 0,
                "ac_power_in": 0,
                "ac_output": PortStatus.NOT_CONNECTED,
                "ac_power_out": 0,
                "solar_port": PortStatus.NOT_CONNECTED,
                "solar_power_in": 0,
                "usb_port_c1": PortStatus.NOT_CONNECTED,
                "usb_c1_power": 0,
                "usb_port_c2": PortStatus.NOT_CONNECTED,
                "usb_c2_power": 0,
                "usb_port_c3": PortStatus.NOT_CONNECTED,
                "usb_c3_power": 0,
                "usb_port_a1": PortStatus.NOT_CONNECTED,
                "usb_a1_power": 0,
                "dc_output": PortStatus.NOT_CONNECTED,
                "dc_power_out": 0,
                "max_battery_percentage": 100,
                "min_battery_percentage": 1,
            },
            id="c1000g2",
        ),
        pytest.param(
            C300,
            "a10131a2050300000000a3050300000000a40302ffffa503020000a603025400a703020000a803020000a903020000aa03020100ab03020000ac03020000ad03020000ae03025500af03020000b003020100b103021b04b20302fc01b30302fc01b403021c00b503027b00b603021b04b7020101b8020100b9020124ba020100bb020164bc020164bd020100be020100bf020100c0020101c1020100c2020100c3020100c4020100c51100415a5653424a30453339323030303438c603024a01c70302a005c803022c01c903023c00ca03020000cb020101cc020100cd020102ce020132cf020100d0020100d1020101",
            {
                "ac_timer_remaining": 0,
                "ac_timer": None,
                "dc_timer_remaining": 0,
                "dc_timer": None,
                "hours_remaining": 1.5,
                "days_remaining": 273,
                "ac_power_in": 0,
                "ac_power_out": 84,
                "ac_output": PortStatus.OUTPUT,
                "usb_c1_power": 0,
                "usb_c2_power": 0,
                "usb_c3_power": 0,
                "usb_a1_power": 1,
                "dc_power_out": 0,
                "solar_power_in": 0,
                "power_in": 0,
                "power_out": 85,
                # "solar_port": PortStatus.NOT_CONNECTED,
                "temperature": 36,
                "charging_status": ChargingStatus.IDLE,
                "battery_percentage": 100,
                "usb_port_c1": PortStatus.NOT_CONNECTED,
                "usb_port_c2": PortStatus.NOT_CONNECTED,
                "usb_port_c3": PortStatus.NOT_CONNECTED,
                "usb_port_a1": PortStatus.OUTPUT,
                "dc_output": PortStatus.NOT_CONNECTED,
                "light": LightStatus.OFF,
                "serial_number": "AZVSBJ0E39200048",
            },
            id="c300_ac_passthrough",
        ),
        pytest.param(
            C300,
            "a10131a2050300000000a3050300000000a403021200a503020000a603025300a703020900a803022000a903021000aa03020000ab03020000ac03020000ad03020000ae03028c00af03020000b003020000b103021b04b20302fc01b30302fc01b403021c00b503027b00b603021b04b7020101b8020100b9020124ba020101bb020164bc020164bd020101be020101bf020101c0020101c1020100c2020100c3020100c4020100c51100415a5653424a30453339323030303438c603024a01c70302a005c803022c01c903023c00ca03020000cb020101cc020100cd020102ce020132cf020100d0020100d1020101",
            {
                "ac_timer_remaining": 0,
                "ac_timer": None,
                "dc_timer_remaining": 0,
                "dc_timer": None,
                "hours_remaining": 1.8,
                "days_remaining": 0,
                "ac_power_in": 0,
                "ac_power_out": 83,
                "ac_output": PortStatus.OUTPUT,
                "usb_c1_power": 9,
                "usb_c2_power": 32,
                "usb_c3_power": 16,
                "usb_a1_power": 0,
                "dc_power_out": 0,
                "solar_power_in": 0,
                "power_in": 0,
                "power_out": 140,
                "software_version": "1.0.5.1",
                # "solar_port": PortStatus.NOT_CONNECTED,
                "temperature": 36,
                "charging_status": ChargingStatus.DISCHARGING,
                "battery_percentage": 100,
                "usb_port_c1": PortStatus.OUTPUT,
                "usb_port_c2": PortStatus.OUTPUT,
                "usb_port_c3": PortStatus.OUTPUT,
                "usb_port_a1": PortStatus.OUTPUT,
                "dc_output": PortStatus.NOT_CONNECTED,
                "light": LightStatus.OFF,
                "serial_number": "AZVSBJ0E39200048",
            },
            id="c300_discharging_ac_usb_load",
        ),
        pytest.param(
            C300,
            "a10131a2050300000000a3050300000000a403021000a503020000a603025600a703020000a803020000a903020000aa03020100ab03023900ac03020000ad03020000ae03029000af03020000b003020000b103021b04b20302fc01b30302fc01b403021c00b503027b00b603021b04b7020101b8020100b9020125ba020101bb02015dbc02015dbd020100be020100bf020100c0020101c1020101c2020100c3020100c4020100c51100415a5653424a30453339323030303438c603024a01c70302a005c803022c01c903023c00ca03020000cb020101cc020101cd020102ce020132cf020100d0020100d1020101",
            {
                "ac_timer_remaining": 0,
                "ac_timer": None,
                "dc_timer_remaining": 0,
                "dc_timer": None,
                "hours_remaining": 1.6,
                "days_remaining": 0,
                "ac_power_in": 0,
                "ac_power_out": 86,
                "ac_output": PortStatus.OUTPUT,
                "usb_c1_power": 0,
                "usb_c2_power": 0,
                "usb_c3_power": 0,
                "usb_a1_power": 1,
                "dc_power_out": 57,
                "solar_power_in": 0,
                "power_in": 0,
                "power_out": 144,
                "software_version": "1.0.5.1",
                # "solar_port": PortStatus.NOT_CONNECTED,
                "temperature": 37,
                "charging_status": ChargingStatus.DISCHARGING,
                "battery_percentage": 93,
                "usb_port_c1": PortStatus.NOT_CONNECTED,
                "usb_port_c2": PortStatus.NOT_CONNECTED,
                "usb_port_c3": PortStatus.NOT_CONNECTED,
                "usb_port_a1": PortStatus.OUTPUT,
                "dc_output": PortStatus.OUTPUT,
                "light": LightStatus.OFF,
                "serial_number": "AZVSBJ0E39200048",
            },
            id="c300_discharging_ac_dc_load",
        ),
        pytest.param(
            C300,
            "a10131a2050300000000a3050300000000a403022200a503020000a603025700a703020000a803021d00a903020000aa03020100ab03020000ac03020000ad03021d00ae03025a00af03020000b003020000b103021b04b20302fc01b30302fc01b403021c00b503027b00b603021b04b7020101b8020100b9020125ba020101bb02015abc02015abd020100be020102bf020100c0020101c1020100c2020100c3020100c4020100c51100415a5653424a30453339323030303438c603024a01c70302a005c803022c01c903023c00ca03020000cb020101cc020100cd020102ce020132cf020102d0020100d1020101",
            {
                "ac_timer_remaining": 0,
                "ac_timer": None,
                "dc_timer_remaining": 0,
                "dc_timer": None,
                "hours_remaining": 3.4,
                "days_remaining": 0,
                "ac_power_in": 0,
                "ac_power_out": 87,
                "ac_output": PortStatus.OUTPUT,
                "usb_c1_power": 0,
                "usb_c2_power": 29,
                "usb_c3_power": 0,
                "usb_a1_power": 1,
                "dc_power_out": 0,
                "solar_power_in": 0,
                "power_in": 29,
                "power_out": 90,
                "software_version": "1.0.5.1",
                # "solar_port": PortStatus.NOT_CONNECTED,
                "temperature": 37,
                "charging_status": ChargingStatus.DISCHARGING,
                "battery_percentage": 90,
                "usb_port_c1": PortStatus.NOT_CONNECTED,
                "usb_port_c2": PortStatus.INPUT,
                "usb_port_c3": PortStatus.NOT_CONNECTED,
                "usb_port_a1": PortStatus.OUTPUT,
                "dc_output": PortStatus.NOT_CONNECTED,
                "light": LightStatus.MEDIUM,
                "serial_number": "AZVSBJ0E39200048",
            },
            id="c300_charging_over_usb_and_light",
        ),
        pytest.param(
            C300,
            "a10131a2050300000000a3050300000000a403020100a503029301a603025400a703020000a803020000a903020000aa03020100ab03020000ac03020000ad03029301ae03025800af03020000b003020100b103021b04b20302fc01b30302fc01b403021c00b503027b00b603021b04b7020101b8020102b9020126ba020102bb020159bc020159bd020100be020100bf020100c0020101c1020100c2020100c3020100c4020100c51100415a5653424a30453339323030303438c603024a01c70302a005c803022c01c903023c00ca03020000cb020101cc020100cd020102ce020132cf020103d0020100d1020101",
            {
                "ac_timer_remaining": 0,
                "ac_timer": None,
                "dc_timer_remaining": 0,
                "dc_timer": None,
                "hours_remaining": 0.1,
                "days_remaining": 0,
                "ac_power_in": 403,
                "ac_power_out": 84,
                "ac_output": PortStatus.OUTPUT,
                "usb_c1_power": 0,
                "usb_c2_power": 0,
                "usb_c3_power": 0,
                "usb_a1_power": 1,
                "dc_power_out": 0,
                "solar_power_in": 0,
                "power_in": 403,
                "power_out": 88,
                "software_version": "1.0.5.1",
                # "solar_port": PortStatus.INPUT,
                "temperature": 38,
                "charging_status": ChargingStatus.CHARGING,
                "battery_percentage": 89,
                "usb_port_c1": PortStatus.NOT_CONNECTED,
                "usb_port_c2": PortStatus.NOT_CONNECTED,
                "usb_port_c3": PortStatus.NOT_CONNECTED,
                "usb_port_a1": PortStatus.OUTPUT,
                "dc_output": PortStatus.NOT_CONNECTED,
                "light": LightStatus.HIGH,
                "serial_number": "AZVSBJ0E39200048",
            },
            id="c300_charging_ac_and_light",
        ),
        pytest.param(
            PrimeCharger160w,
            "a10131a20302e805a303020000a4020100a5080400000000000000a6080400000000000000a7080400000000000000a8020103a9020150aa020100ab090400000f0f0f000000ac0d0401002c0100002c0100000300ad0d0401002c0100002c0100000300ae0d0401002c0100002c0100000300af020100b0020100b1020101b2020101b3020101b40d04fafffbfffafffbfffafffbffb50d04ffffffffffffffffffffffffe0050408000000e10b0480034b53000000000000fe050300000000",
            {
                "usb_port_c1": PortStatus.NOT_CONNECTED,
                "usb_c1_current": 0.0,
                "usb_c1_power": 0.0,
                "usb_c1_voltage": 0.0,
                "usb_port_c2": PortStatus.NOT_CONNECTED,
                "usb_c2_current": 0.0,
                "usb_c2_power": 0.0,
                "usb_c2_voltage": 0.0,
                "usb_port_c3": PortStatus.NOT_CONNECTED,
                "usb_c3_current": 0.0,
                "usb_c3_power": 0.0,
                "usb_c3_voltage": 0.0,
            },
            id="prime_160w_idle",
        ),
        pytest.param(
            PrimeCharger160w,
            "a10131a20302e805a303020000a4020100a5080401e01374003700a608040108236c030b03a7080401d81364003200a8020103a9020150aa020100ab090400000f0f0f000000ac0d0401002c0100002c0100000000ad0d0401002c0100002c0100000203ae0d0401002c0100002c0100000000af020100b0020100b1020101b2020101b3020101b40d0400000000e804000000000000b50d04ffffffffffffffffffffffffe0050408000000e10b0480034b53000000000000fe050300000000",
            {
                "usb_port_c1": PortStatus.OUTPUT,
                "usb_c1_current": 0.116,
                "usb_c1_power": 0.55,
                "usb_c1_voltage": 5.088,
                "usb_port_c2": PortStatus.OUTPUT,
                "usb_c2_current": 0.876,
                "usb_c2_power": 7.79,
                "usb_c2_voltage": 8.968,
                "usb_port_c3": PortStatus.OUTPUT,
                "usb_c3_current": 0.1,
                "usb_c3_power": 0.5,
                "usb_c3_voltage": 5.08,
            },
            id="prime_160w_all_three_charging",
        ),
        pytest.param(
            C300DC,
            "a10131a2050300000000a303020000a403020000a503020000a603020000a703020000a803020000a903020000aa03020000ab03020000ac03020000ad03020000ae03020000af03020000b003020000b103020000b203020000b303020000b403020000b5020180b6020100b7020100b8020100b9020100ba020100bb020100bc020100bd020100be020100bf020100c0020100c1020100c2020100c3110020202020202020202020202020202020c403020000c503020000c603020000c7020100c8020100c9020100ca020100cb03020000cc020100cd020100f7050300000000f815040000000000000000000000000000000000000000",
            {
                "dc_timer_remaining": 0,
                "hours_remaining": 0.0,
                "days_remaining": 0,
                "time_remaining": 0.0,
                "usb_c1_power": 0,
                "usb_c2_power": 0,
                "usb_c3_power": 0,
                "usb_c4_power": 0,
                "usb_a1_power": 0,
                "usb_a2_power": 0,
                "dc_power_out": 0,
                "solar_power_in": 0,
                "power_in": 0,
                "power_out": 0,
                "battery_capacity": 0,
                "software_version": "0",
                "temperature": -128,
                "charging_status": ChargingStatus.IDLE,
                "battery_percentage": 0,
                "battery_health": 0,
                "usb_port_c1": PortStatus.NOT_CONNECTED,
                "usb_port_c2": PortStatus.NOT_CONNECTED,
                "usb_port_c3": PortStatus.NOT_CONNECTED,
                "usb_port_c4": PortStatus.NOT_CONNECTED,
                "usb_port_a1": PortStatus.NOT_CONNECTED,
                "usb_port_a2": PortStatus.NOT_CONNECTED,
                "dc_port": PortStatus.NOT_CONNECTED,
                "device_overload": PortOverload.NONE,
                "serial_number": "                ",
                "device_timeout": 0,
                "display_timeout": 0,
                "display_mode": LightStatus.OFF,
                "light": LightStatus.OFF,
                "temperature_unit": TemperatureUnit.CELSIUS,
                "is_display_on": False,
                "light_timeout": 0,
                "solar_port": PortStatus.NOT_CONNECTED,
                "dc_12v_auto_on": False,
            },
            id="c300_dc_min_values",
        ),
        pytest.param(
            C300DC,
            "a10131a20503ffffffffa30302ffffa40302ffffa50302ffffa60302ffffa70302ffffa80302ffffa90302ffffaa0302ffffab0302ffffac0302ffffad0302ffffae03020000af0302ffffb00302ffffb10302ffffb20302ffffb30302ffffb40302ffffb502017fb6020102b70201ffb80201ffb9020102ba020102bb020102bc020102bd020102be020102bf020102c0020100c102010ac2020100c311007e7e7e7e7e7e7e7e7e7e7e7e7e7e7e7ec40302ffffc50302ffffc603020000c7020104c8020104c9020101ca0201ffcb0302ffffcc020100cd020102f70503fffffffff815040000000000000000000000000000000000000000",
            {
                "dc_timer_remaining": 4294967295,
                "hours_remaining": 1.5,
                "days_remaining": 273,
                "time_remaining": 6553.5,
                "usb_c1_power": 65535,
                "usb_c2_power": 65535,
                "usb_c3_power": 65535,
                "usb_c4_power": 65535,
                "usb_a1_power": 65535,
                "usb_a2_power": 65535,
                "dc_power_out": 65535,
                "solar_power_in": 65535,
                "power_in": 65535,
                "power_out": 65535,
                "battery_capacity": 65535,
                "software_version": "6.5.5.3.5",
                "temperature": 127,
                "charging_status": ChargingStatus.CHARGING,
                "battery_percentage": 255,
                "battery_health": 255,
                "usb_port_c1": PortStatus.INPUT,
                "usb_port_c2": PortStatus.INPUT,
                "usb_port_c3": PortStatus.INPUT,
                "usb_port_c4": PortStatus.INPUT,
                "usb_port_a1": PortStatus.INPUT,
                "usb_port_a2": PortStatus.INPUT,
                "dc_port": PortStatus.INPUT,
                "device_overload": PortOverload.USB_C3,
                "serial_number": "~~~~~~~~~~~~~~~~",
                "device_timeout": 65535,
                "display_timeout": 65535,
                "display_mode": LightStatus.SOS,
                "light": LightStatus.SOS,
                "temperature_unit": TemperatureUnit.FAHRENHEIT,
                "is_display_on": True,
                "light_timeout": 65535,
                "solar_port": PortStatus.INPUT,
                "dc_12v_auto_on": True,
            },
            id="c300_dc_max_values",
        ),
        pytest.param(
            C300DC,
            "a10131a2050355555555a30302aaaaa403020000a503020100a60302ff00a703020001a803025555a90302ff7faa03020080ab0302aaaaac030200ffad0302feffae03020000af0302ffffb003020f27b10302ffffb20302ffffb30302ffffb40302ffffb50201ffb6020101b70201feb8020101b9020100ba020101bb020102bc020100bd020101be020102bf020100c0020100c1020108c2020100c3110030313233343536373839414243444546c403023930c5030231D4c60302ffffc7020101c8020102c9020100ca0201ffcb03027b00cc020100cd020101f70503fffffffff815040000000000000000000000000000000000000000",
            {
                "dc_timer_remaining": 1431655765,
                "hours_remaining": 1.0,
                "days_remaining": 182,
                "time_remaining": 4369.0,
                "usb_c1_power": 0,
                "usb_c2_power": 1,
                "usb_c3_power": 255,
                "usb_c4_power": 256,
                "usb_a1_power": 21845,
                "usb_a2_power": 32767,
                "dc_power_out": 32768,
                "solar_power_in": 43690,
                "power_in": 65280,
                "power_out": 65534,
                "battery_capacity": 65535,
                "software_version": "9.9.9.9",
                "temperature": -1,
                "charging_status": ChargingStatus.DISCHARGING,
                "battery_percentage": 254,
                "battery_health": 1,
                "usb_port_c1": PortStatus.NOT_CONNECTED,
                "usb_port_c2": PortStatus.OUTPUT,
                "usb_port_c3": PortStatus.INPUT,
                "usb_port_c4": PortStatus.NOT_CONNECTED,
                "usb_port_a1": PortStatus.OUTPUT,
                "usb_port_a2": PortStatus.INPUT,
                "dc_port": PortStatus.NOT_CONNECTED,
                "device_overload": PortOverload.USB_C1,
                "serial_number": "0123456789ABCDEF",
                "device_timeout": 12345,
                "display_timeout": 54321,
                "display_mode": LightStatus.LOW,
                "light": LightStatus.MEDIUM,
                "temperature_unit": TemperatureUnit.CELSIUS,
                "is_display_on": True,
                "light_timeout": 123,
                "solar_port": PortStatus.INPUT,
                "dc_12v_auto_on": True,
            },
            id="c300_dc_mixed_values",
        ),
        pytest.param(
            Solarbank2,
            "a10131a2110041504347513830453030303030303030a302013aa4020101a503020000a605030100060aa7050300000631a8050300030306a9020100aa020111ab050300000000ac0503f4010000ad02013aae020100af020100b0050300000000b10503e0bd0200b20503723c0a00b305038d840200b4020105b5020104b6020105b7050388130000b8020101b9020100ba050328000000bb020100bc050300000000bd050300000000be050300000000bf050300000000c0110000000000000000000000000000000000c1020100c203022003c40503f4010000c5020100c6020101c703023200c8050300000000c9050306000000ca050300000000cb050300000000cc050300000000cd050300000000d2020100d30503f4010000d4110000000000000000000000000000000000d503020000d6110000000000000000000000000000000000d703020000d8110000000000000000000000000000000000d903020000da110000000000000000000000000000000000db03020000dc110000000000000000000000000000000000dd03020000de110000000000000000000000000000000000df03020000e0020102e1020101e2020100e3020100e4020100e5020100e6020100e7020100e8020100e9020100ea020101fe05039a46d969fb050300000000fc1604010101010001010101010100000000000000000000",
            {
                "serial_number": "APCGQ80E00000000",
                "battery_percentage": 58,
                "battery_percentage_aggregate": 58,
                "error_code": 0,
                "software_version": "1.6.8.1.6.5.3.7.7",
                "software_version_controller": "8.2.2.4.7.6.8.0.0",
                "software_version_expansion": "1.0.0.8.6.0.6.7.2",
                "temperature_unit": TemperatureUnit.CELSIUS,
                "temperature": 17,
                "solar_power_in": 0.0,
                "solar_pv_1_power_in": 0.0,
                "solar_pv_2_power_in": 0.0,
                "solar_pv_3_power_in": 0.0,
                "solar_pv_4_power_in": 0.0,
                "ac_power_out": 50.0,
                "ac_power_out_sockets": 0.0,
                "battery_charge_power": 0.0,
                "battery_discharge_power": 50.0,
                "pv_yield": 17.968,
                "charged_energy": 6.70834,
                "output_energy": 16.5005,
                "grid_to_home_power": 0.0,
                "pv_to_grid_power": 0.0,
                "grid_import_energy": 0.0,
                "grid_export_energy": 0.0,
                "house_demand": 50.0,
                "consumed_energy": 0.0006,
                "power_out": 50.0,
                "max_load": MaxLoadSB2.W800,
                "output_cutoff_data": SBPowerCutoff.P5,
                "lowpower_input_data": 4,
                "input_cutoff_data": SBPowerCutoff.P5,
                "usage_mode": SBUsageMode.MANUAL,
                "home_load_preset": 50,
                "light_mode": LightMode.NORMAL,
                "grid_status": GridStatus.OK_AS_WELL_I_GUESS,
                "light_on": False,
                "battery_heating": False,
            },
            id="solarbank2_telemetry",
        ),
    ],
)
async def test_values(
    device_class: type[SolixBLEDevice], payload: str, mapping: dict[str, Any]
) -> None:
    """
    Test that a payload is parsed into the correct values.

    :param device_class: Class of device under test.
    :param payload: The payload bytes from a telemetry packet.
    :param mapping: Mapping of class properties to their expected value.
    """
    device = device_class(MOCK_BLE_DEVICE)
    parameters = device._parse_payload(bytes.fromhex(payload))
    await device._process_telemetry(parameters)

    for class_property, expected_value in mapping.items():
        assert (
            getattr(device, class_property) == expected_value
        ), f"Mismatch for property '{class_property}'!"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "device_class,packets,secret",
    [
        pytest.param(
            C300,
            [
                "ff090e00030001080100a1010152",
                "ff091b00030001080300a10102a202fd00a30144a40101a50102ff",
                "ff093800030001082900a10103a2054553503332a307302e302e302e33a410415a5653424a30453339323030303438a506f49d8a53a95a14",
                "ff090b00030001080500f2",
                "ff094d00030001082100a140c2a5a88fab34c1ac0f96a52e1b93354a47fb6c674b5afebacf5a2ed755435f41f0d26e97782e54e268b46d9f8a58a267cd7f7a239771e6289e55d94f7669ed448a",
                None,
            ],
            "2e9edc471d11bd214d45c0a651ab42e3cd370e04f1b860fc85adfaf612aba33f",
            id="c300_1",
        ),
        pytest.param(
            C300,
            [
                "ff090e00030001080100a1010152",
                "ff091b00030001080300a10102a202fd00a30144a40101a50102ff",
                "ff093800030001082900a10103a2054553503332a307302e302e302e33a410415a5653424a30453339323030303438a506f49d8a53a95a14",
                "ff090b00030001080500f2",
                "ff094d00030001082100a140a7b5d3824a36cae20bab9fc4d9358191e5351905a782eda157f376cc43f1f761ab772d437f33787188716d1bebd81719d1eb76b94f08499ee93895d5b43e75ef5f",
                None,
            ],
            "f97b0112a955846530c60e4cf95f941df76d86ab9ca106aa4bd00fe1c4fcb14f",
            id="c300_2",
        ),
        pytest.param(
            C1000,
            [
                "ff090e00030001080100a1010152",
                "ff091b00030001080300a10102a202fd00a30144a40101a50102ff",
                "ff093800030001082900a10103a2054553503332a307302e302e302e33a41041504339464530453237333030323735a506f49d8a104e0c9a",
                "ff090b00030001080500f2",
                "ff094d00030001082100a140d3ef70a8faeb9ae7d9be034390108c2c7b177f3d549eb87318bd7a31703fc604664efb0e4600298ca9a905fb5af170955fb76229791dd583478b84d9950bd65420",
                None,
            ],
            "2bdc8c8bfecf40814f602e6547cf29bf125abcc1a93be0751d8f1065a2bb5570",
            id="c1000_1",
        ),
        pytest.param(
            C1000,
            [
                "ff090e00030001080100a1010152",
                "ff091b00030001080300a10102a202fd00a30144a40101a50102ff",
                "ff093800030001082900a10103a2054553503332a307302e302e302e33a41041504339464530453237333030323735a506f49d8a104e0c9a",
                "ff090b00030001080500f2",
                "ff094d00030001082100a140b2ade5cac4f4a0c1307e44a0e9c5363cb21e4c8485ee324c23be949fa5d5929a75e57da3207c948a0c366ca9ea1ab2cb8e57d2d046a6ebefe5d96adb5d4cb35039",
                None,
            ],
            "0c4d9db9ef376fcfe627b9b73089eda514315d4bf67fb7eb299f2894ef7a059c",
            id="c1000_2",
        ),
        pytest.param(
            Solarbank2,
            [
                "ff090e00030001080100a1010152",
                "ff091b00030001080300a10102a202fd00a30144a40101a50102ff",
                "ff093800030001082900a10103a2054553503332a307302e302e302e33a41041504347513830453030303030303030a50600000000000039",
                "ff090b00030001080500f2",
                "ff094d00030001082100a140f809d676751fba1346f21198c8a583b1ef9b9a617fb804455c388d07090e6dc2976c1bb1cf06aee1f30a3286af9dd80f8f0c594010f60755292addedfe41385972",
                None,
            ],
            "6a2c89888de58cce1e15d98eb22669898ec29bcb1519ce19f950439aac9dbcb5",
            id="solarbank2_1",
        ),
    ],
)
async def test_negotiation(
    fast_sleep,
    fast_timeouts,
    device_class: type[SolixBLEDevice],
    packets: list[str],
    secret: str,
):
    """
    Test negotiation of the shared secret by mocking a device.

    :param device_class: The class of the device being tested.
    :param packets: Packets sent by the mock device in response to our packets.
    :param secret: The expected shared secret.
    """
    async with MockDevice() as mock_bluetooth:

        device = device_class(MOCK_BLE_DEVICE)

        for packet in packets:
            mock_bluetooth.expect_ordered(
                None,
                [bytes.fromhex(packet)] if packet else [],
            )

        # Assert that the connection succeeds
        assert await device.connect(), "Expected connect to return True"

        # Assert that the correct shared secret is calculated
        assert (
            bytes.fromhex(secret) == device._shared_secret
        ), "Shared secret does not match expected"

        mock_bluetooth.check_assertions()


@pytest.mark.parametrize(
    "device_class,payload,secret,decrypted",
    [
        pytest.param(
            C300,
            "5bc7c7b05cf74c1ba441a17a5568f4b25bc061d354f498e39ba509e2c7664ce36d6a9ee8280a40736b9b681f10ab6eb7c86bca4b88fe6fc39ca3391d7ede4e1c47b6b5f0e5ccc67c841a0eb0912039323c27f9e819244424914c9fb538e93a23bc9bfd0f4e9df1b59fec44b5236c75c6f45e42a1110152e56491f8381ae07e50113e3746ca9a16182bc8c9102bbb463eb42d27b1e6330feb3f76d21bf751fe4a1d469c64cd8c9bda426943d48fc7c583c665ea21c7ee23fdde9262d47727c9454d88dd30d291f9bc9b0936a66761846c729f898895d97c158c36e703626ea8499fbf2dc8962159f1b7380f5f84038240d5df00ce1a7eecb4f3ea0b7de9aac5b8637d78f0f3fcf6d600227148d5011bd765a99be6d6ab0e83b9ebe8dcb9ce5ba6",
            "23a6446c34efb9f9ab1dbc43ffc8e289fffdfed557f849c4e91bd7baec0c4814",
            "a10131a2050300000000a3050300000000a40302ffffa503020000a603025b00a703020000a803020000a903020000aa03020000ab03020000ac03020000ad03020000ae03025b00af03020000b003020100b103021b04b20302fc01b30302fc01b403021c00b503027b00b603021b04b7020101b8020100b9020125ba020100bb020164bc020164bd020100be020100bf020100c0020101c1020100c2020100c3020100c4020100c51100415a5653424a30453339323030303438c603024a01c70302a005c803022c01c903023c00ca03020000cb020101cc020100cd020102ce020132cf020100d0020100d1020100d2020100f7050301000000f815040101010100010000000000000000000000000000f9020102",
            id="c300_telemetry",
        ),
        pytest.param(
            C1000,
            "403d9e7311afd074672804704798c421db698f11a5a0fc4bd793c127871c6eea7a970666c9b614c494e62b15770b1dba3dc98019e34cf0eb0ebecb5a2c5bc9ae39441d5e5acad73a645112b779312966513b53ba6f78c0f82cda624cce3b08a1a83416bd52fa4caf37e05cfaa9b37ddea75447be949ba10b892c320398fae0191c1290af0e79791c56c0d2217aafb9259b13cd2ccb9e4d520548eb416f4f96b9d852231578d4d516495564215c297fce97549986ef47058168d77afddc8ac5c0b59c9bfaf681a4cd60eca4bfad743731ca81849b83689e452e68f82fcab9fa2404f05f22b557b73705d16bab42b8045ffcc8083f9cb4fa4acda9997de1a40a2eac55b5dfbc70d882874c1db1990b76ae009bb1997ab507d347c84f3fd39d6f6c",
            "0c4d9db9ef376fcfe627b9b73089eda514315d4bf67fb7eb299f2894ef7a059c",
            "a10131a2050300000000a3050300000000a40302d104a503020000a603020000a703020000a803020000a903020000aa03020000ab03020000ac03020000ad03020000ae03020000af03020000b003020300b103020000b203020100b30302a600b403020000b50302ff01b60302ff01b703020000b803029a00b903020000ba0302a600bb03020000bc020100bd020123be020100bf020101c0020100c1020164c2020100c3020164c4020100c5020100c6020100c7020100c8020100c9020100ca020100cb020100cc020100cd020100ce020100cf020100d0110041504339464530453237333030323735e5020100f7050301000000f815040202010100010000000000000000000000000000f9020102fd0b0041313736315f33304168",
            id="c1000_telemetry",
        ),
        pytest.param(
            C1000,
            "a9fdb7f5f88e0d7ec2c3a36f9cb4f226",
            "cf9b34f93bc679b84c9754a9484a56991cef242c586b23dbef195ba0f2ee02cb",
            "00a10131",
            id="c1000_cmd_ack_ac_on",
        ),
        pytest.param(
            C1000,
            "2eb0fc833d00ca9e33491eab73ccfda202cfdedb86599ba5d0e3c2c059652818",
            "cf9b34f93bc679b84c9754a9484a56991cef242c586b23dbef195ba0f2ee02cb",
            "a10131a2020101a3020100a4020100a5020103a6020101e5020100",
            id="c1000_unknown",
        ),
        pytest.param(
            PrimeCharger160w,
            "57e9a883d95e4bc95b5be2baa1c366331abb9292585357de1f59c997254092ef1372bd5a26ef6b51d61dc87082ca8e7985aacad07f64181902c70c0502de2418e366f5f700b13049d9b857e95c85c66a32d64fcf31c8eead9e025ed69c1440170cca149e038501a9544b1baa044a6a65392e154357e137d917fc834e019012a01b9bd18d5ca7dc22bdb0204b0629b3f738f34bafdc26f6bb0781cec80fe547674a6a7a341a018ce3ac81e6eb6b5110d3311db692d174fe363acec5ba606a24b975c2bb2a43ddfe5351f54d9fcd295709",
            "09486817d949a232b58b47a43cc72d045a617a26f3999d30e1d27e38eae52265",
            "a10131a20302e805a303020000a4020100a508040150235704eb03a6080400000000000000a7080400000000000000a8020103a9020150aa020100ab090400000f0f0f000000ac0d0401002c0100002c0100000203ad0d0401002c0100002c0100000300ae0d0401002c0100002c0100000300af020100b0020100b1020101b2020101b3020101b40d04e8040000fafffbfffafffbffb50d04ffffffffffffffffffffffffe0050408000000e10b0480034b53000000000000fe050300000000",
            id="prime_160w_telemetry",
        ),
        # Different anker prime charger from other tests
        pytest.param(
            PrimeCharger160w,
            "14676a53fc1315457c58163660d5b7bb4a6c83be2f8511d2bc79e2428827907a591b28a709df413e4fa633dc943dd7d2902c46bdcd69ea2bfe4c529f577dfe492d3192aa04f2b2a66fa745b4ed64d34a0a8100d4dd165514edd14499cf1243fbc9d1c216239bc53b756256f4dc04723c470a10434d49e3e38c6d6e1c2054a4890ea244a14964ef6b69eecc3ce8debc0f50537a6be461f3a1b9eb6cc1f1303d8dcf9488a8d4c8bc60729fa669974a4b84a50a0d5f75833c157e5e5c54cf19f944e731932e076b25892c13e0b3979ccd11",
            "c0779a39bfa7b290ba9cd3d96b6fdc22a1f6a9746d4fc81e942c3d95",
            "a10131a20302e805a303020000a4020100a5080400000000000000a6080401d84e00000000a7080400000000000000a8020100a9020150aa020100ab090400001c50343b3b3bac0d0401002c0100002c0100000300ad0d0401002c0100002c0100000100ae0d0401002c0100002c0100000300af020101b0020101b1020100b2020101b30201ffb40d04fafffbff00000000fafffbffb50d04ffffffffffffffffffffffffe0050408000000e10b0400000000000000000000fe050300000000",
            id="prime_160w_telemetry_alt",
        ),
    ],
)
def test_payload_decryption(
    device_class: type[SolixBLEDevice], payload: str, secret: str, decrypted: str
):
    """
    Test the decryption of a payload only. This does not test the
    splitting of a packet.

    :param device_class: Class of device under test.
    :param payload: Payload to be decrypted.
    :param secret: Shared secret used for AES key and IV.
    :param decrypted: Expected content of decrypted payload.
    """

    device = device_class(MOCK_BLE_DEVICE)
    device._shared_secret = bytes.fromhex(secret)

    decrypted_bytes = device._decrypt_payload(bytes.fromhex(payload))
    assert decrypted_bytes.hex() == decrypted, "Payloads do not match!"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "device_class, packets, secret, parameters",
    [
        # Test that when there are no packets device._ data is None
        pytest.param(
            SolixBLEDevice,
            [],
            "",
            None,
            id="no_packets",
        ),
        # Test that when there there are 0/2 required packets device._data is None
        pytest.param(
            C1000,
            [
                "ff092a0003010f440156ecb95eb746de03d40ee711ce99f42837a9554c6382d3f5298a3b0648d8536936"
            ],
            "645ca871528991eb38ebb327a781e932b1d9d7a613b04c966b317db056c83428",
            None,
            id="irrelevant_packet_only",
        ),
        # Test that when there there is only 1/2 required packets device._data is None
        pytest.param(
            C1000,
            [
                "ff09390003010fc40222788d127d8418b41a81719975719a26b32734ea4e44ce244683e31928bb9a2736f9ede939567cddce6b3fb0de68116c"
            ],
            "645ca871528991eb38ebb327a781e932b1d9d7a613b04c966b317db056c83428",
            None,
            id="solix_packet_1_missing",
        ),
        # Test that when there there is only 1/2 required packets device._data is None
        pytest.param(
            C1000,
            [
                "ff09fd0003010fc402121e0e23790307a57d4adabcd8d5ad56c3a9ea3cb5b222b0152438ccd3b980eda40fbde184fa66c80c3372dad179f11cad8799858ab95696e52c7e729af87c1106343ed5be9c042c8912b14f3a0d94b32afbed432e66616e1895ba0ff5e74a6da9401117070c926631e5d7886a07bec0de35aeb689e8bb289f1d7854143dc413f25d4b57d290ca4378cfb8efc275aa779145f98956e934eaced2d1f51cef7dd21a340318bfc14fb5f90ffd33e0e484175512af33593b1f91eb9801d7c2e1ac6d56e8fe7e8883d62226484ed6f1af711d042c5e3d0c186b3f2222293bc71ccf4a156a544d5171e90ee9b6b9b8f36ae058b96e3b88"
            ],
            "645ca871528991eb38ebb327a781e932b1d9d7a613b04c966b317db056c83428",
            None,
            id="solix_packet_2_missing",
        ),
        # Test that when the 1st packet arrives after the 2nd packet is it ignored
        pytest.param(
            C1000,
            [
                "ff09390003010fc40222788d127d8418b41a81719975719a26b32734ea4e44ce244683e31928bb9a2736f9ede939567cddce6b3fb0de68116c",
                "ff09fd0003010fc402121e0e23790307a57d4adabcd8d5ad56c3a9ea3cb5b222b0152438ccd3b980eda40fbde184fa66c80c3372dad179f11cad8799858ab95696e52c7e729af87c1106343ed5be9c042c8912b14f3a0d94b32afbed432e66616e1895ba0ff5e74a6da9401117070c926631e5d7886a07bec0de35aeb689e8bb289f1d7854143dc413f25d4b57d290ca4378cfb8efc275aa779145f98956e934eaced2d1f51cef7dd21a340318bfc14fb5f90ffd33e0e484175512af33593b1f91eb9801d7c2e1ac6d56e8fe7e8883d62226484ed6f1af711d042c5e3d0c186b3f2222293bc71ccf4a156a544d5171e90ee9b6b9b8f36ae058b96e3b88",
            ],
            "645ca871528991eb38ebb327a781e932b1d9d7a613b04c966b317db056c83428",
            None,
            id="solix_both_packets_reversed",
        ),
        # Test that when the packets arrive in order they are parsed and device._data is populated
        pytest.param(
            C1000,
            [
                "ff09fd0003010fc402121e0e23790307a57d4adabcd8d5ad56c3a9ea3cb5b222b0152438ccd3b980eda40fbde184fa66c80c3372dad179f11cad8799858ab95696e52c7e729af87c1106343ed5be9c042c8912b14f3a0d94b32afbed432e66616e1895ba0ff5e74a6da9401117070c926631e5d7886a07bec0de35aeb689e8bb289f1d7854143dc413f25d4b57d290ca4378cfb8efc275aa779145f98956e934eaced2d1f51cef7dd21a340318bfc14fb5f90ffd33e0e484175512af33593b1f91eb9801d7c2e1ac6d56e8fe7e8883d62226484ed6f1af711d042c5e3d0c186b3f2222293bc71ccf4a156a544d5171e90ee9b6b9b8f36ae058b96e3b88",
                "ff09390003010fc40222788d127d8418b41a81719975719a26b32734ea4e44ce244683e31928bb9a2736f9ede939567cddce6b3fb0de68116c",
            ],
            "645ca871528991eb38ebb327a781e932b1d9d7a613b04c966b317db056c83428",
            """{'a1': '31', 'a2': '0300000000', 'a3': '0300000000', 'a4': '02720f', 'a5': '020000', 'a6': '020000', 'a7': '020000', 'a8': '020000', 'a9': '020000', 'aa': '020000', 'ab': '020000', 'ac': '020000', 'ad': '020000', 'ae': '020000', 'af': '020000', 'b0': '020100', 'b1': '020000', 'b2': '020100', 'b3': '02a600', 'b4': '020000', 'b5': '02ff01', 'b6': '02ff01', 'b7': '020000', 'b8': '029a00', 'b9': '020000', 'ba': '02a600', 'bb': '020000', 'bc': '0100', 'bd': '0122', 'be': '0100', 'bf': '0101', 'c0': '0100', 'c1': '0164', 'c2': '0100', 'c3': '0164', 'c4': '0100', 'c5': '0100', 'c6': '0100', 'c7': '0100', 'c8': '0100', 'c9': '0100', 'ca': '0100', 'cb': '0100', 'cc': '0100', 'cd': '0100', 'ce': '0100', 'cf': '0100', 'd0': '0041504339464530453237333030323735', 'e5': '0100', 'f7': '0301000000', 'f8': '040202010100010000000000000000000000000000', 'f9': '0102', 'fd': '0041313736315f33304168'}""",
            id="solix_both_packets",
        ),
        # Test that when the packets arrive in order they are parsed and device._data is populated
        # but that the later packet does not result in any changes to the data because it is not
        # valid until the next telemetry packet arrives
        pytest.param(
            C1000,
            [
                "ff09fd0003010fc402121e0e23790307a57d4adabcd8d5ad56c3a9ea3cb5b222b0152438ccd3b980eda40fbde184fa66c80c3372dad179f11cad8799858ab95696e52c7e729af87c1106343ed5be9c042c8912b14f3a0d94b32afbed432e66616e1895ba0ff5e74a6da9401117070c926631e5d7886a07bec0de35aeb689e8bb289f1d7854143dc413f25d4b57d290ca4378cfb8efc275aa779145f98956e934eaced2d1f51cef7dd21a340318bfc14fb5f90ffd33e0e484175512af33593b1f91eb9801d7c2e1ac6d56e8fe7e8883d62226484ed6f1af711d042c5e3d0c186b3f2222293bc71ccf4a156a544d5171e90ee9b6b9b8f36ae058b96e3b88",
                "ff09390003010fc40222788d127d8418b41a81719975719a26b32734ea4e44ce244683e31928bb9a2736f9ede939567cddce6b3fb0de68116c",
                "ff09fd0003010fc402121e0e23790307a57d4adabcd8d5ad56c3218e598b95b4b8aa7ff3483fd3cfc72612b49fad1e5e27b50be913da3b73328c0db3e5f58c5a86dce0f36a9c080db786c1b917a8541d43aec30c6cbd2b229876255894ac5269fb9f3d4258450905bbe28781c5544d7eb57553bc5c39418d02fba353983a9b0f318e951d57ccc019cea984f9a64b0cb793bec8c696936b16fac2d72c59c4b95561f5f534c448f911d5e1c9ac30601e04fb2338313498d083cc6f676b0797b587ebc5e2fc32e60562f5e41e44682b5f8f094bcbea33e0926f304366d5df28c4868d00ba37eb754c9921e9b63ebb0bb1fb76f644c0760636df1303362106",
            ],
            "645ca871528991eb38ebb327a781e932b1d9d7a613b04c966b317db056c83428",
            """{'a1': '31', 'a2': '0300000000', 'a3': '0300000000', 'a4': '02720f', 'a5': '020000', 'a6': '020000', 'a7': '020000', 'a8': '020000', 'a9': '020000', 'aa': '020000', 'ab': '020000', 'ac': '020000', 'ad': '020000', 'ae': '020000', 'af': '020000', 'b0': '020100', 'b1': '020000', 'b2': '020100', 'b3': '02a600', 'b4': '020000', 'b5': '02ff01', 'b6': '02ff01', 'b7': '020000', 'b8': '029a00', 'b9': '020000', 'ba': '02a600', 'bb': '020000', 'bc': '0100', 'bd': '0122', 'be': '0100', 'bf': '0101', 'c0': '0100', 'c1': '0164', 'c2': '0100', 'c3': '0164', 'c4': '0100', 'c5': '0100', 'c6': '0100', 'c7': '0100', 'c8': '0100', 'c9': '0100', 'ca': '0100', 'cb': '0100', 'cc': '0100', 'cd': '0100', 'ce': '0100', 'cf': '0100', 'd0': '0041504339464530453237333030323735', 'e5': '0100', 'f7': '0301000000', 'f8': '040202010100010000000000000000000000000000', 'f9': '0102', 'fd': '0041313736315f33304168'}""",
            id="solix_both_packets_later_invalidates",
        ),
        # Test that when the packets arrive in order they are parsed and device._data is populated
        # but that the later packet does not result in any changes to the data because it is out
        # of order
        pytest.param(
            C1000,
            [
                "ff09fd0003010fc402121e0e23790307a57d4adabcd8d5ad56c3a9ea3cb5b222b0152438ccd3b980eda40fbde184fa66c80c3372dad179f11cad8799858ab95696e52c7e729af87c1106343ed5be9c042c8912b14f3a0d94b32afbed432e66616e1895ba0ff5e74a6da9401117070c926631e5d7886a07bec0de35aeb689e8bb289f1d7854143dc413f25d4b57d290ca4378cfb8efc275aa779145f98956e934eaced2d1f51cef7dd21a340318bfc14fb5f90ffd33e0e484175512af33593b1f91eb9801d7c2e1ac6d56e8fe7e8883d62226484ed6f1af711d042c5e3d0c186b3f2222293bc71ccf4a156a544d5171e90ee9b6b9b8f36ae058b96e3b88",
                "ff09390003010fc40222788d127d8418b41a81719975719a26b32734ea4e44ce244683e31928bb9a2736f9ede939567cddce6b3fb0de68116c",
                "ff09390003010fc40222922d054e0b6cd682ba63ba7cc0e158113a569150aa95c5a21bc3142c1ba2e95c06a7ce78547448520ae8cc1a2844fa",
                "ff09fd0003010fc402121e0e23790307a57d4adabcd8d5ad56c3218e598b95b4b8aa7ff3483fd3cfc72612b49fad1e5e27b50be913da3b73328c0db3e5f58c5a86dce0f36a9c080db786c1b917a8541d43aec30c6cbd2b229876255894ac5269fb9f3d4258450905bbe28781c5544d7eb57553bc5c39418d02fba353983a9b0f318e951d57ccc019cea984f9a64b0cb793bec8c696936b16fac2d72c59c4b95561f5f534c448f911d5e1c9ac30601e04fb2338313498d083cc6f676b0797b587ebc5e2fc32e60562f5e41e44682b5f8f094bcbea33e0926f304366d5df28c4868d00ba37eb754c9921e9b63ebb0bb1fb76f644c0760636df1303362106",
            ],
            "645ca871528991eb38ebb327a781e932b1d9d7a613b04c966b317db056c83428",
            """{'a1': '31', 'a2': '0300000000', 'a3': '0300000000', 'a4': '02720f', 'a5': '020000', 'a6': '020000', 'a7': '020000', 'a8': '020000', 'a9': '020000', 'aa': '020000', 'ab': '020000', 'ac': '020000', 'ad': '020000', 'ae': '020000', 'af': '020000', 'b0': '020100', 'b1': '020000', 'b2': '020100', 'b3': '02a600', 'b4': '020000', 'b5': '02ff01', 'b6': '02ff01', 'b7': '020000', 'b8': '029a00', 'b9': '020000', 'ba': '02a600', 'bb': '020000', 'bc': '0100', 'bd': '0122', 'be': '0100', 'bf': '0101', 'c0': '0100', 'c1': '0164', 'c2': '0100', 'c3': '0164', 'c4': '0100', 'c5': '0100', 'c6': '0100', 'c7': '0100', 'c8': '0100', 'c9': '0100', 'ca': '0100', 'cb': '0100', 'cc': '0100', 'cd': '0100', 'ce': '0100', 'cf': '0100', 'd0': '0041504339464530453237333030323735', 'e5': '0100', 'f7': '0301000000', 'f8': '040202010100010000000000000000000000000000', 'f9': '0102', 'fd': '0041313736315f33304168'}""",
            id="solix_both_packets_later_out_of_order",
        ),
        # Test that when the packets arrive in order they are parsed and device._data is populated
        # but that the later non-telemetry packet does not result in any changes because it is
        # not a telemetry packet
        pytest.param(
            C1000,
            [
                "ff09fd0003010fc402121e0e23790307a57d4adabcd8d5ad56c3a9ea3cb5b222b0152438ccd3b980eda40fbde184fa66c80c3372dad179f11cad8799858ab95696e52c7e729af87c1106343ed5be9c042c8912b14f3a0d94b32afbed432e66616e1895ba0ff5e74a6da9401117070c926631e5d7886a07bec0de35aeb689e8bb289f1d7854143dc413f25d4b57d290ca4378cfb8efc275aa779145f98956e934eaced2d1f51cef7dd21a340318bfc14fb5f90ffd33e0e484175512af33593b1f91eb9801d7c2e1ac6d56e8fe7e8883d62226484ed6f1af711d042c5e3d0c186b3f2222293bc71ccf4a156a544d5171e90ee9b6b9b8f36ae058b96e3b88",
                "ff09390003010fc40222788d127d8418b41a81719975719a26b32734ea4e44ce244683e31928bb9a2736f9ede939567cddce6b3fb0de68116c",
                "ff091a0003010f484a6e744378c57c16ca8ab3a40bebb6f39807",
            ],
            "645ca871528991eb38ebb327a781e932b1d9d7a613b04c966b317db056c83428",
            """{'a1': '31', 'a2': '0300000000', 'a3': '0300000000', 'a4': '02720f', 'a5': '020000', 'a6': '020000', 'a7': '020000', 'a8': '020000', 'a9': '020000', 'aa': '020000', 'ab': '020000', 'ac': '020000', 'ad': '020000', 'ae': '020000', 'af': '020000', 'b0': '020100', 'b1': '020000', 'b2': '020100', 'b3': '02a600', 'b4': '020000', 'b5': '02ff01', 'b6': '02ff01', 'b7': '020000', 'b8': '029a00', 'b9': '020000', 'ba': '02a600', 'bb': '020000', 'bc': '0100', 'bd': '0122', 'be': '0100', 'bf': '0101', 'c0': '0100', 'c1': '0164', 'c2': '0100', 'c3': '0164', 'c4': '0100', 'c5': '0100', 'c6': '0100', 'c7': '0100', 'c8': '0100', 'c9': '0100', 'ca': '0100', 'cb': '0100', 'cc': '0100', 'cd': '0100', 'ce': '0100', 'cf': '0100', 'd0': '0041504339464530453237333030323735', 'e5': '0100', 'f7': '0301000000', 'f8': '040202010100010000000000000000000000000000', 'f9': '0102', 'fd': '0041313736315f33304168'}""",
            id="solix_both_packets_irrelevant_ignored",
        ),
        # Test that when the packets arrive in order they are parsed and device._data is populated
        # and that once both of the next packets are received the device._data changes.
        pytest.param(
            C1000,
            [
                "ff09fd0003010fc402121e0e23790307a57d4adabcd8d5ad56c3a9ea3cb5b222b0152438ccd3b980eda40fbde184fa66c80c3372dad179f11cad8799858ab95696e52c7e729af87c1106343ed5be9c042c8912b14f3a0d94b32afbed432e66616e1895ba0ff5e74a6da9401117070c926631e5d7886a07bec0de35aeb689e8bb289f1d7854143dc413f25d4b57d290ca4378cfb8efc275aa779145f98956e934eaced2d1f51cef7dd21a340318bfc14fb5f90ffd33e0e484175512af33593b1f91eb9801d7c2e1ac6d56e8fe7e8883d62226484ed6f1af711d042c5e3d0c186b3f2222293bc71ccf4a156a544d5171e90ee9b6b9b8f36ae058b96e3b88",
                "ff09390003010fc40222788d127d8418b41a81719975719a26b32734ea4e44ce244683e31928bb9a2736f9ede939567cddce6b3fb0de68116c",
                "ff09fd0003010fc402121e0e23790307a57d4adabcd8d5ad56c3218e598b95b4b8aa7ff3483fd3cfc72612b49fad1e5e27b50be913da3b73328c0db3e5f58c5a86dce0f36a9c080db786c1b917a8541d43aec30c6cbd2b229876255894ac5269fb9f3d4258450905bbe28781c5544d7eb57553bc5c39418d02fba353983a9b0f318e951d57ccc019cea984f9a64b0cb793bec8c696936b16fac2d72c59c4b95561f5f534c448f911d5e1c9ac30601e04fb2338313498d083cc6f676b0797b587ebc5e2fc32e60562f5e41e44682b5f8f094bcbea33e0926f304366d5df28c4868d00ba37eb754c9921e9b63ebb0bb1fb76f644c0760636df1303362106",
                "ff09390003010fc40222922d054e0b6cd682ba63ba7cc0e158113a569150aa95c5a21bc3142c1ba2e95c06a7ce78547448520ae8cc1a2844fa",
            ],
            "645ca871528991eb38ebb327a781e932b1d9d7a613b04c966b317db056c83428",
            """{'a1': '31', 'a2': '0300000000', 'a3': '0300000000', 'a4': '02d80e', 'a5': '020000', 'a6': '020000', 'a7': '020000', 'a8': '020000', 'a9': '020000', 'aa': '020000', 'ab': '020000', 'ac': '020000', 'ad': '020000', 'ae': '020000', 'af': '020000', 'b0': '020100', 'b1': '020000', 'b2': '020100', 'b3': '02a600', 'b4': '020000', 'b5': '02ff01', 'b6': '02ff01', 'b7': '020000', 'b8': '029a00', 'b9': '020000', 'ba': '02a600', 'bb': '020100', 'bc': '0100', 'bd': '0122', 'be': '0100', 'bf': '0101', 'c0': '0100', 'c1': '0164', 'c2': '0100', 'c3': '0164', 'c4': '0100', 'c5': '0100', 'c6': '0100', 'c7': '0100', 'c8': '0100', 'c9': '0100', 'ca': '0100', 'cb': '0100', 'cc': '0100', 'cd': '0100', 'ce': '0100', 'cf': '0100', 'd0': '0041504339464530453237333030323735', 'e5': '0100', 'f7': '0301000000', 'f8': '040202010100010000000000000000000000000000', 'f9': '0102', 'fd': '0041313736315f33304168'}""",
            id="solix_both_packets_with_update",
        ),
        # Test an Anker Prime device (single payload device) with a single telemetry packet.
        pytest.param(
            PrimeCharger160w,
            [
                "ff09da00030111430057e9a883d95e4bc95b5be2baa1c366331abb929258ab5077108dc197254092ef1372bd5a26ef6b51d61dc87082ca8e7985aacad07f64181902c70c0502de2418e366f5f700b13049d9b857e95c85c66a32d64fcf31c8eead9e025ed69c1440170cca149e038501a9544b1baa044a6a65392e154357e137d917fc834e019012a01b9bd18d5ca7dc22bdb0204b0629b3f738f34bafdc26f6bb0781cec80fe547674a6a7a341a018ce3ac81e6eb6b5110d3311db692d174fe363acec5ba606a24b92dcc95a6cdd8fee1843a26694ddd23ac74"
            ],
            "09486817d949a232b58b47a43cc72d045a617a26f3999d30e1d27e38eae52265",
            """{'a1': '31', 'a2': '02e805', 'a3': '020000', 'a4': '0100', 'a5': '0401a824fe0b3f0b', 'a6': '0400000000000000', 'a7': '0400000000000000', 'a8': '0103', 'a9': '0150', 'aa': '0100', 'ab': '0400000f0f0f000000', 'ac': '0401002c0100002c0100000203', 'ad': '0401002c0100002c0100000300', 'ae': '0401002c0100002c0100000300', 'af': '0100', 'b0': '0100', 'b1': '0101', 'b2': '0101', 'b3': '0101', 'b4': '04e8040000fafffbfffafffbff', 'b5': '04ffffffffffffffffffffffff', 'e0': '0408000000', 'e1': '0480034b53000000000000', 'fe': '0300000000'}""",
            id="prime_telemetry_packet",
        ),
    ],
)
async def test_telemetry_packet_processing(
    fast_sleep,
    fast_timeouts,
    device_class: type[SolixBLEDevice],
    packets: list[str],
    secret: str,
    parameters: str | None,
):
    """
    Test the _process_notification function when processing telemetry
    packets end to end.

    :param device_class: Class of device under test.
    :param packets: List of packets to send to device.
    :param secret: Shared secret used as AES key and IV.
    :param parameters: Expected parameters in string form.
    """

    device = device_class(MOCK_BLE_DEVICE)

    negotiation_responses = (
        NEGOTIATION_RESPONSES_PRIME
        if issubclass(device_class, PrimeDevice)
        else NEGOTIATION_RESPONSES_SOLIX
    )

    async with MockDevice() as mock_bluetooth:

        # We first expect a negotiation
        for expected, response in negotiation_responses.items():
            mock_bluetooth.expect_ordered(
                bytes.fromhex(expected),
                [bytes.fromhex(x) for x in response],
            )

        # We expect the negotiations to succeed
        assert await device.connect(), "Expected connect to return True"
        await asyncio.sleep(0.5)
        assert device.connected, "Expected connected to be True"
        assert device.negotiated, "Expected connected to be True"
        mock_bluetooth.check_assertions()

        device._shared_secret = bytes.fromhex(secret)

        for packet in packets:
            await mock_bluetooth.send_data([bytes.fromhex(packet)])

    device_parameters = (
        device._parameters_to_str(device._data) if device._data else None
    )

    assert parameters == device_parameters, "Parameters do not match expected!"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "device_class,payload,mapping,errors",
    [
        # Test that if the a4 value is missing (time remaining) that all the
        # other values are still parsable
        pytest.param(
            C1000,
            "a10131a2050300000000a3050300000000a503020000a603020000a703020000a803020000a903020000aa03020000ab03020000ac03020000ad03020000ae03020000af03020000b003020100b103020000b203020000b30302a600b403020000b503020000b60302ff01b703020000b803029a00b903020000ba0302a600bb03020000bc020100bd020117be020100bf020101c0020100c1020157c2020100c3020164c4020100c5020100c6020100c7020100c8020100c9020100ca020100cb020100cc020100cd020100ce020100cf020100d0110041504339464530453237333030323735e5020100",
            {
                "battery_percentage": 87,
            },
            ["Failed to parse property", "TIME_REMAINING: KeyError: 'a4'"],
            id="c1000_missing_parameter",
        ),
        # Test that if the a2 value is too big (AC timer) that all the
        # other values are still parsable
        pytest.param(
            C1000,
            "a10131a207FFFFFFFFFFFFFFa3050300000000a403026b06a503020000a603020000a703020000a803020000a903020000aa03020000ab03020000ac03020000ad03020000ae03020000af03020000b003020100b103020000b203020000b30302a600b403020000b503020000b60302ff01b703020000b803029a00b903020000ba0302a600bb03020000bc020100bd020117be020100bf020101c0020100c1020157c2020100c3020164c4020100c5020100c6020100c7020100c8020100c9020100ca020100cb020100cc020100cd020100ce020100cf020100d0110041504339464530453237333030323735e5020100",
            {
                "battery_percentage": 87,
            },
            [
                "Failed to parse property",
                "AC_TIMER: OverflowError: Python int too large to convert to C int",
            ],
            id="c1000_invalid_int",
        ),
        # Test that if the d0 value is not a string format (serial number)
        # that all the other values are still parsable
        pytest.param(
            C1000,
            "a10131a2050300000000a3050300000000a403026b06a503020000a603020000a703020000a803020000a903020000aa03020000ab03020000ac03020000ad03020000ae03020000af03020000b003020100b103020000b203020000b30302a600b403020000b503020000b60302ff01b703020000b803029a00b903020000ba0302a600bb03020000bc020100bd020117be020100bf020101c0020100c1020157c2020100c3020164c4020100c5020100c6020100c7020100c8020100c9020100ca020100cb020100cc020100cd020100ce020100cf020100d01100FF504339464530453237333030323735e5020100",
            {
                "battery_percentage": 87,
            },
            [
                "Failed to parse property",
                "SERIAL_NUMBER: UnicodeDecodeError: 'ascii' codec can't decode byte 0xff in position 0: ordinal not in range(128)",
            ],
            id="c1000_invalid_string",
        ),
        # Test that if the bb value is not a valid port status (ac output)
        # that all the other values are still parsable
        pytest.param(
            C1000,
            "a10131a2050300000000a3050300000000a403026b06a503020000a603020000a703020000a803020000a903020000aa03020000ab03020000ac03020000ad03020000ae03020000af03020000b003020100b103020000b203020000b30302a600b403020000b503020000b60302ff01b703020000b803029a00b903020000ba0302a600bb03020005bc020100bd020117be020100bf020101c0020100c1020157c2020100c3020164c4020100c5020100c6020100c7020100c8020100c9020100ca020100cb020100cc020100cd020100ce020100cf020100d0110041504339464530453237333030323735e5020100",
            {
                "battery_percentage": 87,
            },
            [
                "Failed to parse property",
                "AC_OUTPUT: ValueError: 1280 is not a valid PortStatus",
            ],
            id="c1000_invalid_port_status",
        ),
    ],
)
async def test_bad_values(
    caplog,
    device_class: type[SolixBLEDevice],
    payload: str,
    mapping: dict[str, Any],
    errors: list[str],
) -> None:
    """
    Test that a payload with unexpected, invalid, or missing parameter values
    does not result in the rest of the parameters failing to be updated.

    Sometimes unexpected values are found (e.g it turns out the C300 has
    another charging state I did not know about that I found when it
    had a tiny solar input 0w), when this happens it should not
    prevent all of the other values from being populated.

    :param device_class: Class of device under test.
    :param payload: The payload bytes from a telemetry packet.
    :param mapping: Mapping of class properties to their expected value.
    :param errors: List of expected error strings in logs.
    """

    caplog.set_level(logging.DEBUG)

    device = device_class(MOCK_BLE_DEVICE)
    parameters = device._parse_payload(bytes.fromhex(payload))
    await device._process_telemetry(parameters)

    for class_property, expected_value in mapping.items():
        assert (
            getattr(device, class_property) == expected_value
        ), f"Mismatch for property '{class_property}'!"


# Solarbank 2 set-schedule payload (0x405e) and Solarbank2Prime construction
# Synthetic user IDs - never the real Anker cloud userId from any capture.
_FAKE_SB2_USER_ID_STR = "0" * 40
_FAKE_SB2_USER_ID_BYTES = b"f" * 40
_FAKE_SB2_USER_ID_ENV = "1" * 40


def test_sb2_build_set_schedule_payload_matches_expected_layout():
    """A 90 W uniform schedule produces the documented 7-day TLV layout.

    Asserts the per-day-symmetric reading: 7 identical day-blocks
    (a3, a7, ab, af, b3, b7, bb) each with enable flag, 8-byte struct,
    per-day flag, 1-byte trailer; then the ``fd 05 03 <4B>`` nonce.
    """
    fixed_nonce = bytes.fromhex("00112233")
    with mock.patch.object(os, "urandom", return_value=fixed_nonce):
        result = Solarbank2Common._build_set_schedule_payload(90)

    # 8-byte struct for power=90: start=0, end=1440, power=90, const=80.
    struct_hex = "0000a0055a005000"

    def day_block(base: int) -> str:
        return (
            f"{base:02x}020101"
            f"{base + 1:02x}0904{struct_hex}"
            f"{base + 2:02x}020100"
            f"{base + 3:02x}0104"
        )

    expected_hex = (
        "a10121"
        "a2020101"
        + "".join(day_block(0xa3 + 4 * d) for d in range(7))
        + "fd050300112233"
    )
    assert result.hex() == expected_hex


@pytest.mark.parametrize("bad_power", [-1, 801, 1000])
def test_sb2_build_set_schedule_payload_rejects_out_of_range(bad_power):
    """Out-of-range wattage raises ValueError."""
    with pytest.raises(ValueError):
        Solarbank2Common._build_set_schedule_payload(bad_power)


def test_sb2_build_set_schedule_payload_uses_fresh_nonce_per_call():
    """Each call generates a fresh fd nonce (prevents 'abnormal state').

    The Anker app generates fresh random bytes per write; reusing a value
    causes the schedule storage to update but the inverter target to stay
    stuck at the previous value.
    """
    a = Solarbank2Common._build_set_schedule_payload(100)
    b = Solarbank2Common._build_set_schedule_payload(100)
    assert a[:-4] == b[:-4]
    # 1-in-2^32 false-fail rate is negligible.
    assert a[-4:] != b[-4:]


def test_sb2_prime_user_id_explicit_str_encoded_as_ascii():
    dev = Solarbank2Prime(MOCK_BLE_DEVICE, anker_user_id=_FAKE_SB2_USER_ID_STR)
    assert dev._anker_user_id == _FAKE_SB2_USER_ID_STR.encode("ascii")


def test_sb2_prime_user_id_explicit_bytes_kept_as_is():
    dev = Solarbank2Prime(MOCK_BLE_DEVICE, anker_user_id=_FAKE_SB2_USER_ID_BYTES)
    assert dev._anker_user_id == _FAKE_SB2_USER_ID_BYTES


def test_sb2_prime_user_id_falls_back_to_env_var(monkeypatch):
    monkeypatch.setenv(ENV_SB2_ANKER_USER_ID, _FAKE_SB2_USER_ID_ENV)
    dev = Solarbank2Prime(MOCK_BLE_DEVICE)
    assert dev._anker_user_id == _FAKE_SB2_USER_ID_ENV.encode("ascii")


def test_sb2_prime_user_id_missing_raises(monkeypatch):
    monkeypatch.delenv(ENV_SB2_ANKER_USER_ID, raising=False)
    with pytest.raises(ValueError, match="Anker"):
        Solarbank2Prime(MOCK_BLE_DEVICE)


def test_sb2_prime_static_key_encrypt_round_trips(monkeypatch):
    """``_encrypt_with_static_key`` output is decryptable using the same
    Prime static GCM parameters.

    The GCM tag verifying on decrypt is what proves key/nonce/AAD are
    wired correctly. ``_decrypt_payload`` falls back to ``NEGOTIATION_KEY``
    when ``_shared_secret`` is not yet set, mirroring the path used to
    read RX 48xx handshake responses.
    """
    monkeypatch.setenv(ENV_SB2_ANKER_USER_ID, _FAKE_SB2_USER_ID_ENV)
    dev = Solarbank2Prime(MOCK_BLE_DEVICE)
    assert dev._shared_secret is None  # static-key path

    plaintext = bytes.fromhex("a104deadbeefa200")
    encrypted = dev._encrypt_with_static_key(plaintext)

    # GCM output = ciphertext + 16-byte tag.
    assert len(encrypted) == len(plaintext) + 16
    assert dev._decrypt_payload(encrypted) == plaintext
