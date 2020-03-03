"""Support for Modbus."""
import logging
import threading

from .modbus_rs485pi import ModbusRtu
# from pymodbus.transaction import ModbusRtuFramer
import voluptuous as vol

from homeassistant.const import (
    ATTR_STATE,
    CONF_HOST,
    CONF_METHOD,
    CONF_NAME,
    CONF_PORT,
    CONF_TIMEOUT,
    CONF_TYPE,
    EVENT_HOMEASSISTANT_START,
    EVENT_HOMEASSISTANT_STOP,
)
import homeassistant.helpers.config_validation as cv

_LOGGER = logging.getLogger(__name__)

ATTR_ADDRESS = "address"
ATTR_HUB = "hub"
ATTR_UNIT = "unit"
ATTR_VALUE = "value"

CONF_BAUDRATE = "baudrate"
CONF_BYTESIZE = "bytesize"
CONF_HUB = "hub"
CONF_PARITY = "parity"
CONF_STOPBITS = "stopbits"
CONF_RTSMODE = "rtsmode"
CONF_RTSPIN = "rtspin"
CONF_RTSDELAY = "rtsdelay"

DEFAULT_HUB = "default"
DOMAIN = "modbus-rs485"

SERVICE_WRITE_COIL = "write_coil"
SERVICE_WRITE_REGISTER = "write_register"

BASE_SCHEMA = vol.Schema({vol.Optional(CONF_NAME, default=DEFAULT_HUB): cv.string})

SERIAL_SCHEMA = BASE_SCHEMA.extend(
    {
        vol.Required(CONF_BAUDRATE): cv.positive_int,
        vol.Required(CONF_BYTESIZE): vol.Any(5, 6, 7, 8),
        # vol.Required(CONF_METHOD): vol.Any("rtu", "ascii"),
        vol.Required(CONF_PORT): cv.string,
        vol.Required(CONF_PARITY): vol.Any("E", "O", "N"),
        vol.Required(CONF_STOPBITS): vol.Any(1, 2),
        # vol.Required(CONF_TYPE): "serial",
        vol.Optional(CONF_TIMEOUT, default=3): cv.socket_timeout,
        vol.Optional(CONF_RTSMODE, default="N"): vol.Any("N", "U", "D"),
        vol.Optional(CONF_RTSPIN, default=0): cv.positive_int,
        vol.Optional(CONF_RTSDELAY, default=0): cv.positive_int
    }
)

CONFIG_SCHEMA = vol.Schema(
    {DOMAIN: vol.All(cv.ensure_list, [vol.Any(SERIAL_SCHEMA)])},
    extra=vol.ALLOW_EXTRA,
)

SERVICE_WRITE_REGISTER_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_HUB, default=DEFAULT_HUB): cv.string,
        vol.Required(ATTR_UNIT): cv.positive_int,
        vol.Required(ATTR_ADDRESS): cv.positive_int,
        vol.Required(ATTR_VALUE): vol.Any(
            cv.positive_int, vol.All(cv.ensure_list, [cv.positive_int])
        ),
    }
)

SERVICE_WRITE_COIL_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_HUB, default=DEFAULT_HUB): cv.string,
        vol.Required(ATTR_UNIT): cv.positive_int,
        vol.Required(ATTR_ADDRESS): cv.positive_int,
        vol.Required(ATTR_STATE): cv.boolean,
    }
)


# modbus:
#   name: hub1
#   type: serial
#   method: rtu
#   port: /dev/ttyUSB0
#   baudrate: 9600
#   stopbits: 1
#   bytesize: 8
#   parity: N
def setup_client(client_config):
    """Set up modbus client."""
    return ModbusRtu(
        device=client_config[CONF_PORT],
        baud=client_config[CONF_BAUDRATE],
        stop_bit=client_config[CONF_STOPBITS],
        data_bit=client_config[CONF_BYTESIZE],
        parity=client_config[CONF_PARITY],
        rts_mode=client_config[CONF_RTSMODE],
        rts_pin=client_config[CONF_RTSPIN],
        rts_delayus=client_config[CONF_RTSDELAY],
    )


def setup(hass, config):
    """Set up Modbus component."""
    hass.data[DOMAIN] = hub_collect = {}

    for client_config in config[DOMAIN]:
        client = setup_client(client_config)
        name = client_config[CONF_NAME]
        hub_collect[name] = ModbusHub(client, name)
        _LOGGER.debug("Setting up hub: %s", client_config)

    def stop_modbus(event):
        """Stop Modbus service."""
        for client in hub_collect.values():
            client.close()

    def start_modbus(event):
        """Start Modbus service."""
        for client in hub_collect.values():
            client.connect()

        hass.bus.listen_once(EVENT_HOMEASSISTANT_STOP, stop_modbus)

        # Register services for modbus
        hass.services.register(
            DOMAIN,
            SERVICE_WRITE_REGISTER,
            write_register,
            schema=SERVICE_WRITE_REGISTER_SCHEMA,
        )
        hass.services.register(
            DOMAIN, SERVICE_WRITE_COIL, write_coil, schema=SERVICE_WRITE_COIL_SCHEMA
        )

    def write_register(service):
        """Write Modbus registers."""
        slave = service.data.get(ATTR_UNIT)
        address = service.data.get(ATTR_ADDRESS)
        value = service.data.get(ATTR_VALUE)
        client_name = service.data.get(ATTR_HUB)
        if isinstance(value, list):
            hub_collect[client_name].write_registers(slave, address, value)
        else:
            hub_collect[client_name].write_register(slave, address, value)

    def write_coil(service):
        """Write Modbus coil."""
        slave = service.data.get(ATTR_UNIT)
        address = service.data.get(ATTR_ADDRESS)
        state = service.data.get(ATTR_STATE)
        client_name = service.data.get(ATTR_HUB)
        hub_collect[client_name].write_coil(slave, address, state)

    hass.bus.listen_once(EVENT_HOMEASSISTANT_START, start_modbus)

    return True


class ModbusHub:
    """Thread safe wrapper class."""

    def __init__(self, modbus_client: ModbusRtu, name: str):
        """Initialize the Modbus hub."""
        self._client = modbus_client
        self._lock = threading.Lock()
        self._name = name

    @property
    def name(self):
        """Return the name of this hub."""
        return self._name

    def close(self):
        """Disconnect client."""
        with self._lock:
            self._client.close()
            self._client.free()

    def connect(self):
        """Connect client."""
        with self._lock:
            self._client.connect()

    def read_coils(self, slave, address, count):
        """Read coils."""
        with self._lock:
            self._client.set_slave(slave)
            return self._client.read_bits(address, count)

    def read_input_registers(self, slave, address, count):
        """Read input registers."""
        with self._lock:
            self._client.set_slave(slave)
            return self._client.read_input_registers(address, count)

    def read_holding_registers(self, slave, address, count):
        """Read holding registers."""
        with self._lock:
            self._client.set_slave(slave)
            return self._client.read_registers(address, count)

    def write_coil(self, slave, address, value):
        """Write coil."""
        with self._lock:
            self._client.set_slave(slave)
            self._client.write_bit(address, value)

    def write_register(self, slave, address, value):
        """Write register."""
        with self._lock:
            self._client.set_slave(slave)
            self._client.write_register(address, value)

    def write_registers(self, slave, address, values):
        """Write registers."""
        with self._lock:
            self._client.set_slave(slave)
            self._client.write_registers(address, values)
