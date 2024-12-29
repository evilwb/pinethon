"""
The PINE API.
This is the client side implementation of the PINE protocol.
It allows for a three-way communication between the emulated game, the emulator and an external
tool, using the external tool as a relay for all communication. It is a socket based IPC that
is _very_ fast.

If you want to draw comparisons you can think of this as an equivalent of the BizHawk LUA API,
although with the logic out of the core and in an external tool. While BizHawk would run a lua
script at each frame in the core of the emulator we opt instead to keep the entire logic out of
the emulator to make it more easily extensible, more portable, require less code and be more
performant.
"""
import os
from array import array
from enum import IntEnum
from platform import system
import socket


class Pine:
    """ Exposes PS2 memory within a running instance of the PCSX2 emulator using the Pine IPC Protocol. """

    """ Maximum memory used by an IPC message request. Equivalent to 50,000 Write64 requests. """
    MAX_IPC_SIZE: int = 650000

    """ Maximum memory used by an IPC message reply. Equivalent to 50,000 Read64 replies. """
    MAX_IPC_RETURN_SIZE: int = 450000

    """ Maximum number of commands sent in a batch message. """
    MAX_BATCH_REPLY_COUNT: int = 50000

    class IPCResult(IntEnum):
        """ IPC result codes. A list of possible result codes the IPC can send back. Each one of them is what we call an
        "opcode" or "tag" and is the first byte sent by the IPC to differentiate between results.
        """
        IPC_OK = 0,  # IPC command successfully completed.
        IPC_FAIL = 0xFF  # IPC command failed to complete.

    class IPCCommand(IntEnum):
        READ8 = 0,
        READ16 = 1,
        READ32 = 2,
        READ64 = 3,
        WRITE8 = 4,
        WRITE16 = 5,
        WRITE32 = 6,
        WRITE64 = 7,
        VERSION = 8,
        SAVE_STATE = 9,
        LOAD_STATE = 0xA,
        TITLE = 0xB,
        ID = 0xC,
        UUID = 0xD,
        GAME_VERSION = 0xE,
        STATUS = 0xF,
        UNIMPLEMENTED = 0xFF,

    class DataSize(IntEnum):
        INT8 = 1,
        INT16 = 2,
        INT32 = 4,
        INT64 = 8,

    def __init__(self, slot: int = 28011):
        if not 0 < slot <= 65536:
            raise ValueError("Provided slot number is outside valid range")
        self._slot: int = slot
        self._sock: socket.socket
        self._sock_state: bool = False
        self.ret_buffer = array("B", [0]*self.MAX_IPC_RETURN_SIZE)
        self.ipc_buffer = array("B", [0]*self.MAX_IPC_SIZE)
        self.batch_arg_place = array("I", [0]*self.MAX_BATCH_REPLY_COUNT)
        self._init_socket()


    def _init_socket(self) -> None:
        if system() == "Windows":
            socket_family = socket.AF_INET
            socket_name = ("127.0.0.1", self._slot)
        elif system() == "Linux":
            socket_family = socket.AF_UNIX
            socket_name = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
            socket_name += "/pcsx2.sock"
        elif system() == "Darwin":
            socket_family = socket.AF_UNIX
            socket_name = os.environ.get("TMPDIR", "/tmp")
            socket_name += "/pcsx2.sock"
        else:
            socket_family = socket.AF_UNIX
            socket_name = "/tmp/pcsx2.sock"

        try:
            self._sock = socket.socket(socket_family, socket.SOCK_STREAM)
            self._sock.settimeout(1.0)
            self._sock.connect(socket_name)
        except socket.error:
            self._sock.close()
            self._sock_state = False
            return

        self._sock_state = True

    def read(self, data_size: DataSize, address: int) -> bytes:
        if data_size is Pine.DataSize.INT8:
            request = Pine._create_request(Pine.IPCCommand.READ8, address, 9)
        elif data_size is Pine.DataSize.INT16:
            request = Pine._create_request(Pine.IPCCommand.READ16, address, 9)
        elif data_size is Pine.DataSize.INT32:
            request = Pine._create_request(Pine.IPCCommand.READ32, address, 9)
        elif data_size is Pine.DataSize.INT64:
            request = Pine._create_request(Pine.IPCCommand.READ64, address, 9)
        else:
            raise ValueError(f"{data_size} is not a valid data size.")

        if not self._sock_state:
            self._init_socket()

        try:
            self._sock.sendall(request)
        except socket.error:
            self._sock.close()
            self._sock_state = False
            raise ConnectionError("Lost connection to PCSX2.")

        end_length = 4
        result: bytes = b''
        while len(result) < end_length:
            try:
                response = self._sock.recv(4096)
            except TimeoutError:
                raise TimeoutError("Response timed out. "
                                   "This might be caused by having two PINE connections open on the same slot")

            if len(response) <= 0:
                result = b''
                break

            result += response

            if end_length == 4 and len(response) >= 4:
                end_length = Pine.from_array(result[0:4], 4)
                if end_length > Pine.MAX_IPC_SIZE:
                    result = b''
                    break

        if len(result) == 0:
            raise ConnectionError("Invalid response from PCSX2.")
        if result[4] == Pine.IPCResult.IPC_FAIL:
            raise ConnectionError("Failure indicated in PCSX2 response.")

        return result

    def write(self, data_size: DataSize, address: int, data: int) -> None:
        if data_size is Pine.DataSize.INT8:
            request = Pine._create_request(Pine.IPCCommand.WRITE8, address, 9 + data_size)
        elif data_size is Pine.DataSize.INT16:
            request = Pine._create_request(Pine.IPCCommand.WRITE16, address, 9 + data_size)
        elif data_size is Pine.DataSize.INT32:
            request = Pine._create_request(Pine.IPCCommand.WRITE32, address, 9 + data_size)
        elif data_size is Pine.DataSize.INT64:
            request = Pine._create_request(Pine.IPCCommand.WRITE64, address, 9 + data_size)
        else:
            raise ValueError(f"{data_size} is not a valid data size.")

        request += Pine.to_array(data, data_size)

        if not self._sock_state:
            self._init_socket()

        try:
            self._sock.sendall(request)
        except socket.error:
            self._sock.close()
            self._sock_state = False
            raise ConnectionError("Lost connection to PCSX2.")

        end_length = 4
        result: bytes = b''
        while len(result) < end_length:
            try:
                response = self._sock.recv(4096)
            except TimeoutError:
                raise TimeoutError("Response timed out. "
                                   "This might be caused by having two PINE connections open on the same slot")

            if len(response) <= 0:
                result = b''
                break

            result += response

            if end_length == 4 and len(response) >= 4:
                end_length = Pine.from_array(result[0:4], 4)
                if end_length > Pine.MAX_IPC_SIZE:
                    result = b''
                    break

        if len(result) == 0:
            raise ConnectionError("Invalid response from PCSX2.")
        if result[4] == Pine.IPCResult.IPC_FAIL:
            raise ConnectionError("Failure indicated in PCSX2 response.")


    @staticmethod
    def _create_request(command: IPCCommand, address: int, size: int = 0) -> bytes:
        ipc = Pine.to_array(size, 4)
        ipc += Pine.to_array(command, 1)
        ipc += Pine.to_array(address, 4)
        return ipc

    @staticmethod
    def to_array(value: int, size: int) -> bytes:
        return value.to_bytes(length=size, byteorder="little")

    @staticmethod
    def from_array(arr: bytes, size: int) -> int:
        return int.from_bytes(arr, byteorder="little")




