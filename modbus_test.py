from modbus_rs485pi import ModbusRtu
import time

if __name__ == '__main__':
    rtu = ModbusRtu("/dev/ttyAMA1", 57600, "N", 8, 1, "U", 7, 100)
    rtu.set_slave(1)
    rtu.connect()
    t = time.perf_counter()
    for _ in range(100):
        x = rtu.read_bits(1, 5)
    print('Elapsed:' + str(time.perf_counter() - t))
    for i in x:
        print(i)
    rtu.close()
    rtu.free()
