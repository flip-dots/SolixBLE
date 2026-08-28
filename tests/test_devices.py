"""Tests for the parsing of a decrypted telemetry packet into device attributes.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any
from unittest import mock

import pytest

from SolixBLE import (
    C300,
    C300DC,
    C800,
    C1000,
    C1000G2,
    F2000Old,
    F2600,
    ChargingStatus,
    DisplayTimeout,
    LightStatus,
    MagGo3in1,
    PortOverload,
    PortStatus,
    PrimeCharger160w,
    PrimeCharger250w,
    PrimeDevice,
    PrimePowerBank20k,
    Solarbank2,
    SolixBLEDevice,
    TemperatureUnit,
)
from SolixBLE.devices.f2000_old import (
    AcOutputCommand,
    AcTimerCommand,
    CommandAck,
    CommandType,
    Header,
    Output,
    PollExtendedCommand,
    PowerSaveCommand,
    StateAck,
    Telemetry,
    TwelveVoltOutputCommand,
)
from SolixBLE.devices.f3800 import F3800
from SolixBLE.devices.solarbank2 import MaxLoadSB2
from SolixBLE.states import GridStatus, LightMode, SBPowerCutoff, SBUsageMode
from tests.const import (
    MOCK_BLE_DEVICE,
    NEGOTIATION_RESPONSES_PRIME,
    NEGOTIATION_RESPONSES_SOLIX,
)
from tests.helpers import MockDevice


F2000_OLD_TELEMETRY = "09ff0000010149660000000000000000005ab90000ce01000000000000000000000000000000000000ce0100000000d7006a0074006b00000033030000d7000100021c00000064006400000000000000000000000030313032303330343035303630373038a2"
F2000_OLD_EXTENDED = "09ff00000101017a0000000000000000005ab90000ce01000000000000000000000000000000000000ce0100000000d7006a0074006b00000033030000d7000100021c0000006400640000000000000000000000003031303230333034303530363037303858023c001e003c00010001000100023c00000100a0"


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
        # The two cases below are decrypted telemetry frames captured from a real
        # C1000 Gen 2 (A1763) on 2026-06-21 with the AC output physically off then
        # on (idle, no load). They are identical except for the "a7" param, which
        # locks in the AC output decode: ac_output is "a7" byte 1 (00=off, 01=on,
        # latched) -- the same per-port "04 <status> <watts LE>" shape used by the
        # DC port (b2) and USB ports. ("a4" byte 22 is NOT the AC state: it stayed
        # 01 with the port physically off, so an a4-based decode reports a false
        # OUTPUT.)
        pytest.param(
            C1000G2,
            "a10131a221062011415043444b39363047313631303033393000054131373633030401010100a30e0400000000b0040064cc00580200a41b0400000000580232010000000000f0003c00010000000100500a00a506042400396400a60a04000000000000ab2a39a70704000000000000a80404000000aa0404000000ab0404000000ac0404000000ae0404000000b20404000000d91a04000019500a0000000000000000000000000000000000000000da18040000000000000000000001e00164057f00000000000000dc06040000000000f91d0403040101060005000000000000000000090300010000000006090200fa15040101010100170300000000000000000000000000fd0e0031373832303439353930383637fe050364f4376a",
            {
                "serial_number": "APCDK960G16100390",
                "part_number": "A1763",
                "temperature": 36,
                "battery_percentage": 57,
                "battery_health": 100,
                "ac_output": PortStatus.NOT_CONNECTED,
                "ac_power_in": 0,
                "ac_power_out": 0,
                "power_out": 0,
                "solar_port": PortStatus.NOT_CONNECTED,
                "dc_output": PortStatus.NOT_CONNECTED,
                "max_battery_percentage": 80,
                "min_battery_percentage": 10,
            },
            id="c1000g2_ac_off",
        ),
        pytest.param(
            C1000G2,
            "a10131a221062011415043444b39363047313631303033393000054131373633030401010100a30e0400000000b0040064cc00580200a41b0400000000580232010000000000f0003c00010000000100500a00a506042400396400a60a04000000000000ab2a39a70704010000000000a80404000000aa0404000000ab0404000000ac0404000000ae0404000000b20404000000d91a04000019500a0000000000000000000000000000000000000000da18040000000000000000000001e00164057f00000000000000dc06040000000000f91d0403040101060005000000000000000000090300010000000006090200fa15040101010100170300000000000000000000000000fd0e0031373832303439353930383637fe050369f4376a",
            {
                "serial_number": "APCDK960G16100390",
                "part_number": "A1763",
                "temperature": 36,
                "battery_percentage": 57,
                "battery_health": 100,
                "ac_output": PortStatus.OUTPUT,
                "ac_power_in": 0,
                "ac_power_out": 0,
                "power_out": 0,
                "solar_port": PortStatus.NOT_CONNECTED,
                "dc_output": PortStatus.NOT_CONNECTED,
                "max_battery_percentage": 80,
                "min_battery_percentage": 10,
            },
            id="c1000g2_ac_on",
        ),
        # Derived from the idle "c1000g2" frame above with only the "b2" param
        # changed from 04000000 to 04010600 -- the value observed live on a real
        # C1000 Gen 2 with the DC output on and a ~6 W 12 V load. This locks in
        # the DC decode: dc_output is "b2" byte 1 (01 = OUTPUT) and dc_power_out
        # is "b2" [2:4] little-endian watts (0x0006 = 6 W).
        pytest.param(
            C1000G2,
            "a10134a221062011415043444b39363146333734303032393000054131373633060201010100a30b0400000000b0040058dc00a41b0400000000b0043201000000000000001e00010000000000640103a506041700646400a60a04000000000000ab2a64a70704000000010000a80404000000aa0404000000ab0404000000ac0404000000ae0404000000b20404010600d91a0400001964010000000100000000000000000000000000000000da18040000000000000000000001e00164057f00000000000000dc06040000000000f91d0406020101050005000000000005000500050300010000000000020200fa150401010101001f0300000000000000000000000000fd0e0031373634363538323735393838fe0503638c2e69f0",
            {
                "serial_number": "APCDK961F37400290",
                "battery_percentage": 100,
                "ac_output": PortStatus.NOT_CONNECTED,
                "dc_output": PortStatus.OUTPUT,
                "dc_power_out": 6,
            },
            id="c1000g2_dc_on",
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
            PrimeCharger250w,
            "a10131a2080400000014000000a3080400000014000000a4080400000014000000a5080400000014000000a6080400000000000000a7080400000000000000a81104fafffbfffafffbfffafffbfffafffbffa91104fffffffffffffffffffffffffffffffffe0503ff79b569",
            {
                "usb_port_c1": PortStatus.NOT_CONNECTED,
                "usb_c1_current": 0.02,
                "usb_c1_power": 0.0,
                "usb_c1_voltage": 0.0,
                "usb_port_c2": PortStatus.NOT_CONNECTED,
                "usb_c2_current": 0.02,
                "usb_c2_power": 0.0,
                "usb_c2_voltage": 0.0,
                "usb_port_c3": PortStatus.NOT_CONNECTED,
                "usb_c3_current": 0.02,
                "usb_c3_power": 0.0,
                "usb_c3_voltage": 0.0,
                "usb_port_c4": PortStatus.NOT_CONNECTED,
                "usb_c4_current": 0.02,
                "usb_c4_power": 0.0,
                "usb_c4_voltage": 0.0,
                "usb_port_a1": PortStatus.NOT_CONNECTED,
                "usb_a1_current": 0.0,
                "usb_a1_power": 0.0,
                "usb_a1_voltage": 0.0,
                "usb_port_a2": PortStatus.NOT_CONNECTED,
                "usb_a2_current": 0.0,
                "usb_a2_power": 0.0,
                "usb_a2_voltage": 0.0,
            },
            id="prime_250w_idle",
        ),
        pytest.param(
            PrimeCharger250w,
            "a10131a2080401881329016400a30804014024d8061c06a4080401004d9d08ee10a5080401084d1809b311a6080401801364003100a70804018013b7003100a8110400000000e80400001a290b1100000000a91104ffffffff0200ffff0a000200fffffffffe05033d7ab569",
            {
                "usb_port_c1": PortStatus.OUTPUT,
                "usb_c1_current": 0.297,
                "usb_c1_power": 1.0,
                "usb_c1_voltage": 5.0,
                "usb_port_c2": PortStatus.OUTPUT,
                "usb_c2_current": 1.752,
                "usb_c2_power": 15.64,
                "usb_c2_voltage": 9.28,
                "usb_port_c3": PortStatus.OUTPUT,
                "usb_c3_current": 2.205,
                "usb_c3_power": 43.34,
                "usb_c3_voltage": 19.712,
                "usb_port_c4": PortStatus.OUTPUT,
                "usb_c4_current": 2.328,
                "usb_c4_power": 45.31,
                "usb_c4_voltage": 19.72,
                "usb_port_a1": PortStatus.OUTPUT,
                "usb_a1_current": 0.1,
                "usb_a1_power": 0.49,
                "usb_a1_voltage": 4.992,
                "usb_port_a2": PortStatus.OUTPUT,
                "usb_a2_current": 0.183,
                "usb_a2_power": 0.49,
                "usb_a2_voltage": 4.992,
            },
            id="prime_250w_all_outputs",
        ),
        pytest.param(
            PrimePowerBank20k,
            "a10131a203044d60a30404010000a4020101a50404000000a60404000000a7080400000000000000a80f0400000000009600ff00ffffffff00a90f0400000000000000ff00ffffffff00ac09040000000000000000af02011db002011eb103020900fe050300000000",
            {
                "battery_percentage": 77,
                "temperature": 29,
                "power_out": 0.0,
                "usb_port_c1": PortStatus.NOT_CONNECTED,
                "usb_c1_current": 0.0,
                "usb_c1_power": 15.0,
                "usb_c1_voltage": 0.0,
                "usb_port_c2": PortStatus.NOT_CONNECTED,
                "usb_c2_current": 0.0,
                "usb_c2_power": 0.0,
                "usb_c2_voltage": 0.0,
                "usb_port_a1": PortStatus.NOT_CONNECTED,
                "usb_a1_current": 0.0,
                "usb_a1_power": 0.0,
                "usb_a1_voltage": 0.0,
            },
            id="prime_power_bank_20k_idle",
        ),
        pytest.param(
            PrimePowerBank20k,
            "a10131a20304515ca30404010000a4020101a50404000000a60404013601a7080400000000000000a80f04019500140036010107ffffffff00a90f0400000000000000ff00ffffffff00ac09040000000000000000af02011ab002011bb103020900fe050300000000",
            {
                "battery_percentage": 81,
                "temperature": 26,
                "power_out": 31.0,
                "usb_port_c1": PortStatus.OUTPUT,
                "usb_c1_current": 2.0,
                "usb_c1_power": 31.0,
                "usb_c1_voltage": 14.9,
                "usb_port_c2": PortStatus.NOT_CONNECTED,
                "usb_c2_current": 0.0,
                "usb_c2_power": 0.0,
                "usb_c2_voltage": 0.0,
                "usb_port_a1": PortStatus.NOT_CONNECTED,
                "usb_a1_current": 0.0,
                "usb_a1_power": 0.0,
                "usb_a1_voltage": 0.0,
            },
            id="prime_power_bank_20k_discharge_c1",
        ),
        pytest.param(
            PrimePowerBank20k,
            "a10131a20304505ca30404010000a4020101a50404000000a60404013a01a7080400000000000000a80f0400000000003d01ff00ffffffff00a90f0401950014002a010107ffffffff00ac09040133000300100000af02011bb002011cb103020900fe050300000000",
            {
                "battery_percentage": 80,
                "temperature": 27,
                "power_out": 31.4,
                "usb_port_c1": PortStatus.NOT_CONNECTED,
                "usb_c1_current": 0.0,
                "usb_c1_power": 31.7,
                "usb_c1_voltage": 0.0,
                "usb_port_c2": PortStatus.OUTPUT,
                "usb_c2_current": 2.0,
                "usb_c2_power": 29.8,
                "usb_c2_voltage": 14.9,
                "usb_port_a1": PortStatus.OUTPUT,
                "usb_a1_current": 0.3,
                "usb_a1_power": 1.6,
                "usb_a1_voltage": 5.1,
            },
            id="prime_power_bank_20k_discharge_c2_a1",
        ),
        pytest.param(
            PrimePowerBank20k,
            "a10131a203044b5da30404010018a4020101a50404014102a6040401a300a7080400000000000000a80f04015900100096000107ffffffff00a90f0402c9001c004102ff07ffffffff00ac090401330002000d0000af02011cb002011db103020900fe050300000000",
            {
                "battery_percentage": 75,
                "temperature": 28,
                "power_out": 16.3,
                "usb_port_c1": PortStatus.OUTPUT,
                "usb_c1_current": 1.6,
                "usb_c1_power": 15.0,
                "usb_c1_voltage": 8.9,
                "usb_port_c2": PortStatus.INPUT,
                "usb_c2_current": 2.8,
                "usb_c2_power": 57.7,
                "usb_c2_voltage": 20.1,
                "usb_port_a1": PortStatus.OUTPUT,
                "usb_a1_current": 0.2,
                "usb_a1_power": 1.3,
                "usb_a1_voltage": 5.1,
            },
            id="prime_power_bank_20k_discharge_c1_a1_charge_c2",
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
        # Anker MagGo 3-in-1 wireless charger. Real capture with a phone on pad 1
        # and an Apple Watch on pad 2, pad 3 unused. Per-pad power is the little
        # endian value at aX[6:8] divided by 100 (e.g a2 -> 0x011d = 285 -> 2.85).
        pytest.param(
            MagGo3in1,
            "a10131a20804013a0232001d01a3080401c60214008e00a4080400f40100000000a50304ffffa6050400000000fe050300000000",
            {
                "pad_1": PortStatus.OUTPUT,
                "pad_1_power": 2.85,
                "pad_2": PortStatus.OUTPUT,
                "pad_2_power": 1.42,
                "pad_3": PortStatus.NOT_CONNECTED,
                "pad_3_power": 0.0,
                "power_out": 4.27,
            },
            id="maggo_3in1_phone_and_watch",
        ),
        # Same charger, only pad 2 (a3) differs - phone now drawing more power.
        pytest.param(
            MagGo3in1,
            "a10131a20804013a0232001d01a3080401d0021e00d800a4080400f40100000000a50304ffffa6050400000000fe050300000000",
            {
                "pad_1": PortStatus.OUTPUT,
                "pad_1_power": 2.85,
                "pad_2": PortStatus.OUTPUT,
                "pad_2_power": 2.16,
                "pad_3": PortStatus.NOT_CONNECTED,
                "pad_3_power": 0.0,
                "power_out": 5.01,
            },
            id="maggo_3in1_phone_higher_power",
        ),
        # Captured from a real F2600 charging from the wall at 1440 W with a
        # 280 W load on the AC output, taken from the get_status_update
        # response. Note that a5/a6 are the AC values and af/b0 are the totals,
        # which is the other way around from the F2000 this model inherits
        # from. Both happen to be equal here because AC is the only input.
        pytest.param(
            F2600,
            "a10131a2050300000000a3050300000000a403020900a50302a405a603021801a703020000a803020000a903020000aa03020000ab03020000ac03020000ad03020000ae03020000af0302a405b003021801b103020000b203020000b303025a01b403022e01b503027400b603026c00b703020000b803027500b903020000ba03025a01bb03020100bc020102bd020122be020100bf020102c0020100c1020140c2020100c3020164c4020100c5020100c6020100c7020100c8020100c9020100ca020100cb020100cc020100cd020100ce020100cf020100d01100415a56334e4d30463038373030343131d10302a005d203020000d303021400d403023c00d503020000d603020000d7020101d8020100d9020103da02013cdb020100dc020100dd020101de020100f815040000000001000000000000000000000000000000fd0a0041313738315f354168fe0503372b136a",
            {
                "ac_timer_remaining": 0,
                "ac_timer": None,
                "dc_timer_remaining": 0,
                "dc_timer": None,
                "time_remaining": 0.9,
                "hours_remaining": 0.9,
                "days_remaining": 0,
                "charging_status": ChargingStatus.CHARGING,
                "ac_power_in": 1444,
                "ac_power_out": 280,
                "power_in": 1444,
                "power_out": 280,
                "solar_power_in": 0,
                "solar_port": PortStatus.NOT_CONNECTED,
                "ac_output": PortStatus.OUTPUT,
                "dc_output": PortStatus.NOT_CONNECTED,
                "usb_port_c1": PortStatus.NOT_CONNECTED,
                "usb_port_c2": PortStatus.NOT_CONNECTED,
                "usb_port_c3": PortStatus.NOT_CONNECTED,
                "usb_port_a1": PortStatus.NOT_CONNECTED,
                "usb_port_a2": PortStatus.NOT_CONNECTED,
                "light": LightStatus.OFF,
                "temperature": 34,
                "battery_percentage": 64,
                "battery_health": 100,
                "num_expansion": 0,
                "software_version": "3.4.6",
                "software_version_controller": "3.4.6",
                "serial_number": "AZV3NM0F08700411",
                # Only present in a full status update response.
                "ac_charging_power": 1440,
                "display_timeout": 20,
                "display_mode": LightStatus.HIGH,
                "power_saving_mode_enabled": False,
                "is_display_on": False,
                # The F2000 reads these same keys as something else, which is
                # why the F2600 overrides them.
                "ac_to_battery": 1444,
                "ac_power_out_sockets": 280,
            },
            id="f2600_ac_charging",
        ),
        # Unlike the payload above this one is constructed rather than
        # captured. The key to property mapping it encodes was confirmed
        # against real hardware, but the values are chosen to exercise the
        # parsing, so do not read it as a record of a specific packet.
        #
        # The same device running off solar with a USB load, as reported in an
        # unsolicited telemetry packet. These are shorter than a full status
        # update and omit the configuration parameters (d1, d3, d9, db and de),
        # which is what the missing value fallbacks exist for.
        pytest.param(
            F2600,
            "a2050300000000a3050300000000a403028400a503020000a603020000a703022d00a803020000a903020000aa03020000ab03020500ac03020000ad03020000ae03029600af03029600b003023200b303026a00b903020000ba03026e00bb020100bc020101bd02011cbe020100bf020101c1020159c2020100c3020164c4020100c5020100c6020101c7020100c8020100c9020100ca020101cb020101cf020103d0110041313738314142434445464748323334",
            {
                "time_remaining": 13.2,
                "hours_remaining": 13.2,
                "days_remaining": 0,
                "charging_status": ChargingStatus.DISCHARGING,
                "ac_power_in": 0,
                "ac_power_out": 0,
                "power_in": 150,
                "power_out": 50,
                "solar_power_in": 150,
                "solar_port": PortStatus.INPUT,
                "ac_output": PortStatus.NOT_CONNECTED,
                "dc_output": PortStatus.OUTPUT,
                "usb_c1_power": 45,
                "usb_a2_power": 5,
                "usb_port_c1": PortStatus.OUTPUT,
                "usb_port_a2": PortStatus.OUTPUT,
                "light": LightStatus.HIGH,
                "temperature": 28,
                "battery_percentage": 89,
                # Not reported outside of a full status update response.
                "ac_charging_power": -1,
                "display_timeout": -1,
                "display_mode": LightStatus.UNKNOWN,
                "power_saving_mode_enabled": None,
                "is_display_on": None,
            },
            id="f2600_solar_discharging",
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


@pytest.mark.parametrize(
    ("payload", "mapping"),
    [
        pytest.param(
            F2000_OLD_TELEMETRY,
            {
                "days_remaining": 185,
                "hours_remaining": 9.0,
                "time_remaining": 4449.0,
                "ac_power_in": 0,
                "ac_power_out": 462,
                "ac_output": PortStatus.OUTPUT,
                "solar_power_in": 0,
                "power_in": 0,
                "power_out": 462,
                "dc_power_out": 0,
                "dc_output": PortStatus.NOT_CONNECTED,
                "usb_c1_power": 0,
                "usb_c2_power": 0,
                "usb_c3_power": 0,
                "usb_a1_power": 0,
                "usb_a2_power": 0,
                "temperature": 28,
                "temperature_expansion": None,
                "battery_percentage": 100,
                "battery_percentage_expansion": None,
                "battery_health": 100,
                "charging_status": ChargingStatus.IDLE,
                "software_version": "2.1.5",
                "serial_number": "0102030405060708",
            },
            id="f2000_old_ac_load",
        ),
        pytest.param(
            F2000_OLD_EXTENDED,
            {
                "ac_power_in_limit": 600,
                "screen_timeout": 30,
                "screen_brightness": LightStatus.MEDIUM,
                "power_saving_mode_enabled": False,
                "light": LightStatus.OFF,
                "serial_number": "0102030405060708",
            },
            id="f2000_old_extended",
        ),
    ],
)
def test_f2000_old_values(payload: str, mapping: dict[str, Any]) -> None:
    """Test real F2000 telemetry with its device serial anonymized."""
    device = F2000Old(MOCK_BLE_DEVICE)
    # Telemetry is a class attribute in F2000Old, so isolate each test case.
    device.telemetry = Telemetry()
    device.telemetry.from_bytes(bytes.fromhex(payload))

    for class_property, expected_value in mapping.items():
        assert (
            getattr(device, class_property) == expected_value
        ), f"Mismatch for property '{class_property}'!"


def test_f2000_old_state_and_command_ack() -> None:
    """Test state updates and command acknowledgements captured from an F2000."""
    device = F2000Old(MOCK_BLE_DEVICE)
    device.telemetry = Telemetry()
    device.telemetry.from_bytes(
        bytes.fromhex(F2000_OLD_EXTENDED),
    )
    assert device.telemetry.temperature_unit == TemperatureUnit.FAHRENHEIT

    # AC and DC on, power saving off, and the light at its lowest level.
    device.telemetry.from_bytes(bytes.fromhex("09ff00000101480e000101000062"))
    assert device.ac_output == PortStatus.OUTPUT
    assert device.dc_output == PortStatus.OUTPUT
    assert device.power_saving_mode_enabled is False
    assert device.light == LightStatus.OFF

    device.telemetry.from_bytes(bytes.fromhex("09ff00000102870a009c"))
    assert device.telemetry.last_command_type == CommandType.TWELVE_VOLT_OUTPUT


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "args", "commands"),
    [
        pytest.param("turn_ac_on", (), ["08ee00000002860b00018a"], id="ac_on"),
        pytest.param("turn_ac_off", (), ["08ee00000002860b000089"], id="ac_off"),
        pytest.param("turn_dc_on", (), ["08ee00000002870b00018b"], id="dc_on"),
        pytest.param("turn_dc_off", (), ["08ee00000002870b00008a"], id="dc_off"),
        pytest.param(
            "set_light_mode",
            (LightStatus.HIGH,),
            ["08ee000000028b0b000391", "08ee00000001010a0002"],
            id="light_high",
        ),
        pytest.param(
            "turn_power_saving_mode_on",
            (),
            ["08ee000000028a0b00018e", "08ee00000001010a0002"],
            id="power_saving_on",
        ),
        pytest.param(
            "turn_power_saving_mode_off",
            (),
            ["08ee000000028a0b00008d", "08ee00000001010a0002"],
            id="power_saving_off",
        ),
        pytest.param(
            "set_screen_brightness",
            (LightStatus.MEDIUM,),
            ["08ee00000002880b00028d", "08ee00000001010a0002"],
            id="screen_brightness",
        ),
        pytest.param(
            "set_ac_power_in_limit",
            (600,),
            ["08ee00000002800c005802de", "08ee00000001010a0002"],
            id="ac_power_in_limit",
        ),
        pytest.param(
            "set_screen_timeout",
            (30,),
            ["08ee00000002820c001e00a4", "08ee00000001010a0002"],
            id="screen_timeout",
        ),
        pytest.param(
            "set_dc_timer",
            (timedelta(minutes=30),),
            ["08ee00000002030e000807000018"],
            id="dc_timer",
        ),
    ],
)
async def test_f2000_old_control_commands(
    method: str, args: tuple[Any, ...], commands: list[str],
) -> None:
    """Test that F2000 control methods dispatch their checksummed commands."""
    device = F2000Old(MOCK_BLE_DEVICE)
    device.telemetry = Telemetry()
    device.send_command = mock.AsyncMock()

    await getattr(device, method)(*args)

    actual = [
        call.kwargs["command"].to_bytes().hex()
        for call in device.send_command.await_args_list
    ]
    assert actual == commands


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "args"),
    [
        pytest.param("set_light_mode", (LightStatus.UNKNOWN,), id="light_unknown"),
        pytest.param(
            "set_screen_brightness",
            (LightStatus.UNKNOWN,),
            id="screen_brightness_unknown",
        ),
        pytest.param("set_ac_power_in_limit", (199,), id="ac_limit_too_low"),
        pytest.param("set_ac_power_in_limit", (1441,), id="ac_limit_too_high"),
        pytest.param("set_screen_timeout", (-1,), id="screen_timeout_negative"),
        pytest.param(
            "set_dc_timer",
            (timedelta(seconds=65536),),
            id="dc_timer_too_long",
        ),
    ],
)
async def test_f2000_old_invalid_commands(
    method: str, args: tuple[Any, ...],
) -> None:
    """Test that invalid F2000 commands are rejected before transmission."""
    device = F2000Old(MOCK_BLE_DEVICE)
    device.send_command = mock.AsyncMock()

    with pytest.raises(ValueError, match=r"must be"):
        await getattr(device, method)(*args)

    device.send_command.assert_not_awaited()


def test_f2000_old_command_validation_and_ac_timer() -> None:
    """Test command-only validation branches and AC timer encoding."""
    assert AcTimerCommand(seconds=3600).to_bytes().hex() == (
        "08ee00000002020e00100e000026"
    )

    invalid_commands = (
        lambda: PowerSaveCommand(is_on=2),
        lambda: AcOutputCommand(is_on=-1),
        lambda: TwelveVoltOutputCommand(is_on=2),
        lambda: AcTimerCommand(seconds=65536),
    )
    for make_command in invalid_commands:
        with pytest.raises(ValueError, match=r"must be"):
            make_command()


def test_f2000_old_packet_errors_and_command_telemetry(caplog) -> None:
    """Test short, command-tagged, and malformed telemetry packets."""
    with pytest.raises(ValueError, match="Data length not correct"):
        Header.from_bytes(b"short")
    with pytest.raises(ValueError, match="Data not long enough"):
        Telemetry().from_bytes(b"short")

    command_telemetry = bytearray.fromhex(F2000_OLD_TELEMETRY)
    command_telemetry[6] = CommandType.AC_OUTPUT.value
    command_telemetry[-1] = sum(command_telemetry[:-1]) & 0xFF
    telemetry = Telemetry()
    telemetry.from_bytes(command_telemetry)
    assert telemetry.last_command_type == CommandType.AC_OUTPUT
    assert telemetry.total_output_watts == 462

    unknown_charging_state = bytearray.fromhex(F2000_OLD_TELEMETRY)
    unknown_charging_state[68] = 3
    unknown_charging_state[-1] = sum(unknown_charging_state[:-1]) & 0xFF
    telemetry.from_bytes(unknown_charging_state)
    assert telemetry.charging_status == ChargingStatus.UNKNOWN

    invalid_state_ack = bytearray.fromhex("09ff00000101480e00010100ff61")
    invalid_state_ack[-1] = sum(invalid_state_ack[:-1]) & 0xFF
    telemetry.from_bytes(invalid_state_ack)
    assert "255 is not a valid LightStatus" in caplog.text


def test_f2000_old_ack_pretty_print_helpers() -> None:
    """Test the JSON encoders used by acknowledgment diagnostics."""
    acknowledgements = (
        (CommandAck(CommandType.AC_OUTPUT), CommandType.AC_OUTPUT),
        (
            StateAck(
                ac_outlet_on=True,
                twelve_volt_on=False,
                power_save_on=True,
                light_status=LightStatus.HIGH,
            ),
            LightStatus.HIGH,
        ),
    )

    for acknowledgement, enum_value in acknowledgements:
        with (
            mock.patch(
                "SolixBLE.devices.f2000_old.json.dumps", return_value="encoded",
            ) as dumps,
            mock.patch("builtins.print") as print_mock,
        ):
            acknowledgement.pretty_print()

        print_mock.assert_called_once_with("encoded")
        encoder = dumps.call_args.kwargs["default"]
        assert encoder(enum_value) == str(enum_value)
        with pytest.raises(TypeError, match="is not JSON serializable"):
            encoder(object())


def test_f2000_old_optional_properties_and_output_states() -> None:
    """Test expansion battery, timers, timestamps, and all output states."""
    device = F2000Old(MOCK_BLE_DEVICE)
    device.telemetry = Telemetry()

    device.telemetry.external_battery.percentage = 75
    device.telemetry.external_battery.temperature = 27
    assert device.battery_percentage_expansion == 75
    assert device.temperature_expansion == 27

    device.telemetry.charging_status = ChargingStatus.IDLE
    assert device.timestamp_remaining is None
    device.telemetry.charging_status = ChargingStatus.DISCHARGING
    device.telemetry.battery_remaining = timedelta(minutes=30)
    timestamp = device.timestamp_remaining
    assert timestamp is not None
    assert timedelta(minutes=29) < timestamp - datetime.now() < timedelta(minutes=31)

    device.telemetry.ac_outlet = Output(is_on=False, watts=100)
    device.telemetry.twelve_volt_1 = Output(is_on=False, watts=10)
    device.telemetry.twelve_volt_2 = Output(is_on=False, watts=20)
    assert device.ac_output == PortStatus.NOT_CONNECTED
    assert device.dc_output == PortStatus.NOT_CONNECTED
    assert device.dc_1_power_out == 10
    assert device.dc_2_power_out == 20
    assert device.dc_timer_remaining == -1
    assert device.dc_timer is None

    device.telemetry.twelve_volt_1.time_remaining = timedelta(minutes=15)
    assert device.dc_timer_remaining == 900
    dc_timer = device.dc_timer
    assert dc_timer is not None
    assert timedelta(minutes=14) < dc_timer - datetime.now() < timedelta(minutes=16)

    usb_outputs = (
        "usb_c_1",
        "usb_c_2",
        "usb_c_3",
        "usb_a_1",
        "usb_a_2",
    )
    usb_properties = (
        "usb_port_c1",
        "usb_port_c2",
        "usb_port_c3",
        "usb_port_a1",
        "usb_port_a2",
    )
    for output_name, property_name in zip(usb_outputs, usb_properties, strict=True):
        setattr(device.telemetry, output_name, Output(is_on=False, watts=0))
        assert getattr(device, property_name) == PortStatus.NOT_CONNECTED
        getattr(device.telemetry, output_name).is_on = True
        assert getattr(device, property_name) == PortStatus.OUTPUT

    device.telemetry.power_save_status = None
    assert device.power_saving_mode_enabled is None


@pytest.mark.asyncio
async def test_f2000_old_notification_routing() -> None:
    """Test current-client filtering, callbacks, polling, and parse failures."""
    device = F2000Old(MOCK_BLE_DEVICE)
    device.telemetry = Telemetry()
    client = mock.MagicMock()
    client.is_connected = True
    device._client = client
    callback = mock.Mock()
    device.add_callback(callback)
    device.send_poll_extended = mock.AsyncMock()

    await device._process_notification(mock.MagicMock(), 0, bytearray(b"ignored"))
    callback.assert_not_called()

    await device._process_notification(
        client, 0, bytearray.fromhex(F2000_OLD_TELEMETRY),
    )
    assert device.negotiated is True
    assert device.available is True
    assert device._last_data_timestamp is not None
    callback.assert_called_once_with()
    device.send_poll_extended.assert_awaited_once_with()

    await device._process_notification(client, 0, bytearray(b"short"))
    assert callback.call_count == 2
    device.send_poll_extended.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_f2000_old_send_command_connection_states() -> None:
    """Test direct command transmission and its disconnected guard."""
    device = F2000Old(MOCK_BLE_DEVICE)
    command = PollExtendedCommand()

    with pytest.raises(ConnectionError, match="Not connected"):
        await device.send_command(command)

    client = mock.MagicMock()
    client.is_connected = True
    client.write_gatt_char = mock.AsyncMock()
    device._client = client
    await device.send_command(command)
    client.write_gatt_char.assert_awaited_once_with(
        device.UUID_COMMAND,
        command.to_bytes(),
        response=False,
    )


@pytest.mark.asyncio
async def test_f2600_timers() -> None:
    """
    Test that a running F2600 timer is reported as a timestamp.

    The a2 and a3 keys hold a second count, which the timer properties turn
    into a wall clock timestamp. This is the f2600_ac_charging payload with an
    hour left on the AC timer and half an hour left on the DC timer, as the
    mapping in test_values cannot assert on a moving timestamp.
    """
    device = F2600(MOCK_BLE_DEVICE)
    payload = "a20503100e0000a3050308070000a403022d00a50302b004a603020000a703020000a803020000a903020000aa03020000ab03020000ac03020000ad03020000ae03020000af0302b004b003020000b303026a00b903020000ba03026e00bb020100bc020102bd020119be020100bf020100c102013ec2020100c3020164c4020100c5020100c6020100c7020100c8020100c9020100ca020100cb020100cf020100d0110041313738314142434445464748323334d10302e803d303022c01d9020102db020101de020101"
    await device._process_telemetry(device._parse_payload(bytes.fromhex(payload)))

    assert device.ac_timer_remaining == 3600
    assert device.dc_timer_remaining == 1800

    ac_timer = device.ac_timer
    dc_timer = device.dc_timer
    assert ac_timer is not None, "Expected a timestamp for the running AC timer!"
    assert dc_timer is not None, "Expected a timestamp for the running DC timer!"

    now = datetime.now()
    assert timedelta(minutes=59) < ac_timer - now < timedelta(minutes=61)
    assert timedelta(minutes=29) < dc_timer - now < timedelta(minutes=31)


@pytest.mark.asyncio
async def test_f2600_status_update(fast_sleep, fast_timeouts) -> None:
    """
    Test that a status update response is reassembled and parsed.

    The F2600 splits its telemetry across two packets which get_status_update
    waits for one at a time, so the second can only be delivered once the first
    has been consumed. Both packets are a real capture of the same state as the
    f2600_ac_charging case in test_values.
    """
    packets = [
        "ff09fd0003010fc840121d0c33c131a989f42599468694c5ae12a4fefe22077259298f3d55e53945a587d5b57b6f753bad94f98cb73b83b7f941437047efffcd2e1bc7bf6f5ad6025c100c489d768f32d0b7109149f577d3c421d38cab71f56f327ddfe1d31615c863b5452abfb8fe515afc08e8e020199d6c354f6e87a319c2a2a057f5879ffdfcb250b974a99ed6ac66c5c54f955363a5e36bacaf0b3782cf58dc3bdcf5f92aa034cc946e77a70dae2a6e8d998c69507dce227ec7f4aff4f39246a4471913443d374ffe784731cb561f1a688574a4a2ab18cd22af78bff26debce0132b8bb8c66a9376b67834a07234aad0e437ac6f4a20eb4da9d50",
        "ff09790003010fc84022d9ecf7817f965014c285c67f2b043bb132c112af3837ebb36ffce45ad0714007b23ec0986fa6ca826b67e69c4155622c165f9a906ad30be10677e4796ee324f18529bba09f8df569b8550e58f8fd69055deda4d72d75ae415e699d3290a005cebc3ceed0ba628ac9ebb37d89f3c0d4",
    ]

    device = F2600(MOCK_BLE_DEVICE)

    async with MockDevice() as mock_bluetooth:

        # We first expect a negotiation
        for expected, response in NEGOTIATION_RESPONSES_SOLIX.items():
            mock_bluetooth.expect_ordered(
                bytes.fromhex(expected),
                [bytes.fromhex(x) for x in response],
            )

        assert await device.connect(), "Expected connect to return True"
        await asyncio.sleep(0.5)
        assert device.negotiated, "Expected negotiated to be True"
        mock_bluetooth.check_assertions()

        # Swap in the secret the packets below were captured with
        device._shared_secret = bytes.fromhex(
            "691d425d79574b56e59524c7e2e592701e13441aba03e4d1b251211f113f980c"
        )

        async def wait_until_listening() -> None:
            """Block until the device is waiting for a telemetry packet.

            A packet that arrives before get_status_update has registered a
            future for it is routed as a regular notification and dropped, so
            the packets cannot just be sent one after the other.
            """
            key = bytes.fromhex("03010f") + bytes.fromhex("c840")
            for _ in range(1000):
                if any(
                    not future.done() for future in device._packet_futures.get(key, [])
                ):
                    return
                await asyncio.sleep(0.01)
            raise AssertionError("Device never listened for a telemetry packet!")

        # The request itself gets no response, the packets are fed in
        # afterwards so that they arrive while it is waiting for them
        mock_bluetooth.expect_ordered(None, [])
        update = asyncio.create_task(device.get_status_update())

        for packet in packets:
            await wait_until_listening()
            await mock_bluetooth.send_data([bytes.fromhex(packet)])

        parameters = await update
        mock_bluetooth.check_assertions()

    # The values are asserted on properly by the f2600_ac_charging case in
    # test_values, this only confirms the packets went back together in order
    assert parameters["c1"] == bytes.fromhex("0140"), "Expected 64% battery!"
    assert parameters["d0"] == b"\x00AZV3NM0F08700411", "Expected the serial!"
    assert device._data == parameters, "Expected the update to be stored!"


@pytest.mark.asyncio
async def test_c1000g2_dc_control() -> None:
    """C1000 Gen 2 DC output control dispatches command 4102.

    Confirmed on real hardware (the 12 V port physically switched and acked).
    Here we just lock in that turn_dc_on/off send command 4102 with the same
    on/off payloads as the AC output, which is the only difference between the
    two on the Gen 2.
    """
    device = C1000G2(MOCK_BLE_DEVICE)
    device._send_command = mock.AsyncMock()

    await device.turn_dc_on()
    device._send_command.assert_awaited_once_with(
        cmd=bytes.fromhex("4102"), payload=bytes.fromhex("a10121a2020101")
    )

    device._send_command.reset_mock()
    await device.turn_dc_off()
    device._send_command.assert_awaited_once_with(
        cmd=bytes.fromhex("4102"), payload=bytes.fromhex("a10121a2020100")
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("device_class", "method", "args", "cmd", "payload"),
    [
        pytest.param(
            F2600,
            "turn_ac_on",
            (),
            "404a",
            "a10121a2020101",
            id="f2600_ac_on",
        ),
        pytest.param(
            F2600,
            "turn_ac_off",
            (),
            "404a",
            "a10121a2020100",
            id="f2600_ac_off",
        ),
        pytest.param(
            F2600,
            "turn_dc_on",
            (),
            "404b",
            "a10121a2020101",
            id="f2600_dc_on",
        ),
        pytest.param(
            F2600,
            "turn_dc_off",
            (),
            "404b",
            "a10121a2020100",
            id="f2600_dc_off",
        ),
        pytest.param(
            F2600,
            "turn_display_on",
            (),
            "4052",
            "a10121a2020101",
            id="f2600_display_on",
        ),
        pytest.param(
            F2600,
            "turn_display_off",
            (),
            "4052",
            "a10121a2020100",
            id="f2600_display_off",
        ),
        pytest.param(
            F2600,
            "turn_power_saving_mode_on",
            (),
            "404e",
            "a10121a2020101",
            id="f2600_power_saving_on",
        ),
        pytest.param(
            F2600,
            "turn_power_saving_mode_off",
            (),
            "404e",
            "a10121a2020100",
            id="f2600_power_saving_off",
        ),
        # Timers take a 32 bit little endian second count. Zero cancels.
        pytest.param(
            F2600,
            "set_ac_timer",
            (3600,),
            "4042",
            "a10121a20502100e0000",
            id="f2600_ac_timer_1h",
        ),
        pytest.param(
            F2600,
            "set_ac_timer",
            (0,),
            "4042",
            "a10121a2050200000000",
            id="f2600_ac_timer_cancel",
        ),
        pytest.param(
            F2600,
            "set_dc_timer",
            (1800,),
            "4043",
            "a10121a2050208070000",
            id="f2600_dc_timer_30m",
        ),
        # Light and display brightness take a single byte enum value.
        pytest.param(
            F2600,
            "set_light_mode",
            (LightStatus.OFF,),
            "404f",
            "a10121a2020100",
            id="f2600_light_off",
        ),
        pytest.param(
            F2600,
            "set_light_mode",
            (LightStatus.HIGH,),
            "404f",
            "a10121a2020103",
            id="f2600_light_high",
        ),
        pytest.param(
            F2600,
            "set_display_mode",
            (LightStatus.MEDIUM,),
            "404c",
            "a10121a2020102",
            id="f2600_display_medium",
        ),
        # Display timeout and AC charging power take a 16 bit little endian value.
        pytest.param(
            F2600,
            "set_display_timeout",
            (DisplayTimeout.S300,),
            "4046",
            "a10121a203022c01",
            id="f2600_display_timeout_5m",
        ),
        pytest.param(
            F2600,
            "set_display_timeout",
            (DisplayTimeout.S1800,),
            "4046",
            "a10121a203020807",
            id="f2600_display_timeout_30m",
        ),
        pytest.param(
            F2600,
            "set_ac_charging_power",
            (1000,),
            "4044",
            "a10121a20302e803",
            id="f2600_ac_charging_power_1000w",
        ),
        # Both ends of the accepted range.
        pytest.param(
            F2600,
            "set_ac_charging_power",
            (100,),
            "4044",
            "a10121a203026400",
            id="f2600_ac_charging_power_min",
        ),
        pytest.param(
            F2600,
            "set_ac_charging_power",
            (1440,),
            "4044",
            "a10121a20302a005",
            id="f2600_ac_charging_power_max",
        ),
        pytest.param(
            F3800,
            "turn_ac_on",
            (),
            "404a",
            "a10121a2020101",
            id="f2600_ac_on",
        ),
        pytest.param(
            F3800,
            "turn_ac_off",
            (),
            "404a",
            "a10121a2020100",
            id="f2600_ac_off",
        ),
        pytest.param(
            F3800,
            "turn_dc_on",
            (),
            "404b",
            "a10121a2020101",
            id="f2600_dc_on",
        ),
        pytest.param(
            F3800,
            "turn_dc_off",
            (),
            "404b",
            "a10121a2020100",
            id="f2600_dc_off",
        ),
    ],
)
async def test_control_commands(
    device_class: type[SolixBLEDevice],
    method: str, 
    args: tuple[Any, ...],
    cmd: str, payload: str,
) -> None:
    """
    Test that an F2600 control method dispatches the correct command.

    :param method: Name of the method under test.
    :param args: Positional arguments to call the method with.
    :param cmd: Expected command bytes.
    :param payload: Expected payload bytes.
    """
    device = device_class(MOCK_BLE_DEVICE)
    device._send_command = mock.AsyncMock()
    await getattr(device, method)(*args)

    device._send_command.assert_awaited_once_with(
        cmd=bytes.fromhex(cmd), payload=bytes.fromhex(payload),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,args",
    [
        pytest.param("set_light_mode", (LightStatus.UNKNOWN,), id="light_unknown"),
        pytest.param(
            "set_display_mode",
            (LightStatus.UNKNOWN,),
            id="display_unknown",
        ),
        # The LCD has no SOS brightness, unlike the light bar.
        pytest.param("set_display_mode", (LightStatus.SOS,), id="display_sos"),
        pytest.param(
            "set_display_timeout",
            (DisplayTimeout.UNKNOWN,),
            id="timeout_unknown",
        ),
        # Below 100 W the device charges at full power instead, and 1440 W is
        # the highest the app allows.
        pytest.param("set_ac_charging_power", (99,), id="ac_charging_power_too_low"),
        pytest.param(
            "set_ac_charging_power",
            (1441,),
            id="ac_charging_power_too_high",
        ),
    ],
)
async def test_f2600_invalid_commands(method: str, args: tuple[Any, ...]) -> None:
    """
    Test that an invalid F2600 command is rejected without being transmitted.

    :param method: Name of the method under test.
    :param args: Positional arguments to call the method with.
    """
    device = F2600(MOCK_BLE_DEVICE)
    device._send_command = mock.AsyncMock()

    with pytest.raises(ValueError):
        await getattr(device, method)(*args)

    device._send_command.assert_not_awaited()


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
        pytest.param(
            PrimePowerBank20k,
            [
                "ff091e000300014801ab273ed3e27270c3f4d676ac7d69a00572793732a6",
                "ff092b000300014803ab273ed0443800b35db54c6d4a6ec3d48171a04ea7ebce8bf749e5e48c5d991a5e67",
                "ff0958000300014829ab273ed144326ada9fc66fa02508c5ddf549ade014d1eeb352fea11c0315b70b8aaa8a734ca5830f8d5827acbaa1224f05ad300b38d27bac9862a768d95c29daed0a89e92feb1d09163a094aa700ff",
                "ff091b000300014805abab709a595a803dd04246b78a927453cf65",
                "ff095d000300014821ab277f4e77c3b9e1f44367539f64f85d19969d0273c2c0ca93a06f3a010cf636e3b2df75d10791adf1e3c706a3238bcf0a858cd1e2d55d4cf1164a1b7db3b0058c47dfb24c71f11f8a96209d9f0924d420f03120",
                "ff091b000300014822e520695552c2745a608fd21cf84bc6e3ccb9",
                "ff091b000300014827e520695552c2745a608fd21cf84bc6e3ccbc",
                "ff09df000301114a00e5a17fe3ebb89758b89ffb0e7d35a36ffeaeba3e991d79323680049a018c8e719bb706b6d00a142199a6cdc7f05bb5489f1ebb093fe3d134caf7ae5ad7b456867d9a58885cee8479bc10ea2d42d5b94d3b5a929cf4f4fd25f987e5a4922ae6fa744e22289080676583f390c1351a4b68ac5c1dabdcbf8e5e23416e47a0cea7a6062326dd8505464f821ba881f0f6f2c8ea050a7c978962980a539e90879aa1499b5be92fdceb53de533fc2bdd78b7998aec24493fdcfe3d2bc7e95b383744f92a4168819350e89d0d3142d1dbedcb779e45cfad12008",
                "ff098300030111430044014f704abfd87d1d38fc0d7a35a36efdaf1f9f9f1c799493804dfaa6882d789fb7aeb4d117bd2330cd63c5f13f1e4a089ce80ac2442c66c85fa1f0dcb0d6867d9a58f7a3ee8479ec124724f6d7b84d8a58939c465ffb24e43754a1889be5f8c946d82d93806765835569e75bd67cbd3ac71071159c13a83bb9",
            ],
            "5609bc39f79166da75139feb7c335fb7524b3bf0d730db96bf6ebf450d3e165b",
            id="prime_power_bank_20k",
        ),
        pytest.param(
            F2600,
            [
                "ff090e00030001080100a1010152",
                "ff091b00030001080300a10102a202fd00a30144a40101a50102ff",
                "ff093800030001082900a10103a2054553503332a307302e302e302e33a410415a56334e4d30463038373030343131a506f49d8a9be4862a",
                "ff090b00030001080500f2",
                "ff094d00030001082100a1400f0e69f81a25d11d70396b64b24f4f93b3bb8529b26d68bfdf6355cb0389c121e8560332cc4143c3ebca38ee75961354c28eec75d5585d0b039b66065920133fe3",
                None,
            ],
            "691d425d79574b56e59524c7e2e592701e13441aba03e4d1b251211f113f980c",
            id="f2600_1",
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
        pytest.param(
            PrimePowerBank20k,
            "44014f704abfd87d1d38fc0d7a35a36efdaf1f9f9f1c799493804dfaa6882d789fb7aeb4d117bd2330cd63c5f13f1e4a089ce80ac2442c66c85fa1f0dcb0d6867d9a58f7a3ee8479ec124724f6d7b84d8a58939c465ffb24e43754a1889be5f8c946d82d93806765835569e75bd67cbd3ac71071159c13a83b",
            "5609bc39f79166da75139feb7c335fb7524b3bf0d730db96bf6ebf450d3e165b",
            "a10131a203044d60a30404010000a4020101a50404000000a60404000000a7080400000000000000a80f0400000000009600ff00ffffffff00a90f0400000000000000ff00ffffffff00ac09040000000000000000af02011db002011eb103020900fe050300000000",
            id="prime_power_bank_telemetry",
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
        # Test an Anker Prime power bank (single payload device) with a single telemetry packet.
        pytest.param(
            PrimePowerBank20k,
            [
                "ff098300030111430044014f704abfd87d1d38fc0d7a35a36efdaf1f9f9f1c799493804dfaa6882d789fb7aeb4d117bd2330cd63c5f13f1e4a089ce80ac2442c66c85fa1f0dcb0d6867d9a58f7a3ee8479ec124724f6d7b84d8a58939c465ffb24e43754a1889be5f8c946d82d93806765835569e75bd67cbd3ac71071159c13a83bb9"
            ],
            "5609bc39f79166da75139feb7c335fb7524b3bf0d730db96bf6ebf450d3e165b",
            """{'a1': '31', 'a2': '044d60', 'a3': '04010000', 'a4': '0101', 'a5': '04000000', 'a6': '04000000', 'a7': '0400000000000000', 'a8': '0400000000009600ff00ffffffff00', 'a9': '0400000000000000ff00ffffffff00', 'ac': '040000000000000000', 'af': '011d', 'b0': '011e', 'b1': '020900', 'fe': '0300000000'}""",
            id="prime_power_bank_telemetry_packet",
        ),
        # Test an Anker Prime device (single payload device) with a single telemetry packet
        # from the logs of someone elses unit which for some reason transmits telemetry
        # unencrypted
        pytest.param(
            PrimeCharger160w,
            [
                "ff09ca000301110300a10131a203024606a303020000a4020100a5080401d8459906bb0ba6080401e81300000000a7080400000000000000a8020103a9020150aa020100ab090400000000000b0b0bac0d0401002c0100002c0100000200ad0d0401002c0100002c0100000201ae0d0401002c0100002c0100000300af020100b0020100b1020100b2020101b30201ffb40d0400000000ac051573fafffbffb50d04ffffffffffffffffffffffffe0050448000000e10b0400000000000000000000fe0503000000006b"
            ],
            "5609bc39f79166da75139feb7c335fb7524b3bf0d730db96bf6ebf450d3e165b",
            """{'a1': '31', 'a2': '024606', 'a3': '020000', 'a4': '0100', 'a5': '0401d8459906bb0b', 'a6': '0401e81300000000', 'a7': '0400000000000000', 'a8': '0103', 'a9': '0150', 'aa': '0100', 'ab': '0400000000000b0b0b', 'ac': '0401002c0100002c0100000200', 'ad': '0401002c0100002c0100000201', 'ae': '0401002c0100002c0100000300', 'af': '0100', 'b0': '0100', 'b1': '0100', 'b2': '0101', 'b3': '01ff', 'b4': '0400000000ac051573fafffbff', 'b5': '04ffffffffffffffffffffffff', 'e0': '0448000000', 'e1': '0400000000000000000000', 'fe': '0300000000'}""",
            id="prime_telemetry_packet_plain_text",
        ),
        # Anker MagGo 3-in-1 wireless charger telemetry packet (cmd 4300). The
        # decrypted payload is a real capture (phone on pad 1, watch on pad 2);
        # it was re-encrypted with the secret below to exercise the end-to-end
        # command routing and decrypt/parse path for this device.
        pytest.param(
            MagGo3in1,
            [
                "ff094e00030111430044014f7041bf9427bc0ef8117b960f68fd68b88f9b9279303d80490ea7888a709b12adb02ee81b269cc267c5f1c11b499e9c170a1514a45ceafe1bbd3925d3a766ac4aa32d"
            ],
            "5609bc39f79166da75139feb7c335fb7524b3bf0d730db96bf6ebf450d3e165b",
            """{'a1': '31', 'a2': '04013a0232001d01', 'a3': '0401c60214008e00', 'a4': '0400f40100000000', 'a5': '04ffff', 'a6': '0400000000', 'fe': '0300000000'}""",
            id="maggo_3in1_telemetry_packet",
        ),
        # Same charger, phone now drawing more power (only a3 differs).
        pytest.param(
            MagGo3in1,
            [
                "ff094e00030111430044014f7041bf9427bc0ef8117b960f68fd7eb8859bc479303d80490ea7888a709b12adb02ee81b269cc267c5f1c11b499e9c170a7a6261f98ce9db7373fe83ccb3d81475e2"
            ],
            "5609bc39f79166da75139feb7c335fb7524b3bf0d730db96bf6ebf450d3e165b",
            """{'a1': '31', 'a2': '04013a0232001d01', 'a3': '0401d0021e00d800', 'a4': '0400f40100000000', 'a5': '04ffff', 'a6': '0400000000', 'fe': '0300000000'}""",
            id="maggo_3in1_telemetry_packet_higher_power",
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
    "device_class, packets, secret, expected_logs",
    [
        # Telemetry packet from logs of someone elses Prime 160w charger.
        # Interestingly this packet is not encrypted at all
        pytest.param(
            PrimeCharger160w,
            [
                "ff09ca000301110300a10131a203024606a303020000a4020100a5080401e042b105b209a6080401e81300000000a7080400000000000000a8020103a9020150aa020100ab090400000000000b0b0bac0d0401002c0100002c0100000200ad0d0401002c0100002c0100000201ae0d0401002c0100002c0100000300af020100b0020100b1020100b2020101b30201ffb40d0400000000ac051573fafffbffb50d04ffffffffffffffffffffffffe0050448000000e10b0400000000000000000000fe05030000000074"
            ],
            "5609bc39f79166da75139feb7c335fb7524b3bf0d730db96bf6ebf450d3e165b",
            [
                "Received non-encrypted telemetry message",
                "Telemetry parameters: {'a1': '31', 'a2': '024606'",
            ],
            id="prime_160w_other",
        ),
    ],
)
async def test_generic_packet_processing(
    caplog,
    fast_sleep,
    fast_timeouts,
    device_class: type[SolixBLEDevice],
    packets: list[str],
    secret: str,
    expected_logs: list[str],
):
    """
    Test the _process_notification function when processing arbitrary
    packets and check for expected log entries.

    :param device_class: Class of device under test.
    :param packets: List of packets to send to device.
    :param secret: Shared secret used as AES key and IV.
    :param expected_logs: List of expected entries in the debug log.
    """

    device = device_class(MOCK_BLE_DEVICE)

    negotiation_responses = (
        NEGOTIATION_RESPONSES_PRIME
        if issubclass(device_class, PrimeDevice)
        else NEGOTIATION_RESPONSES_SOLIX
    )

    async with MockDevice() as mock_bluetooth:
        with caplog.at_level(logging.DEBUG):

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

            for expected_log_entry in expected_logs:
                assert (
                    expected_log_entry in caplog.text
                ), f"Expected to find '{expected_log_entry}' in logs but it was not found!"


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
