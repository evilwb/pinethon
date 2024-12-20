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
from array import array
from enum import IntEnum


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

    def __init__(self, slot: int = 28011):
        if not 0 < slot <= 65536:
            raise ValueError("Provided slot number is outside valid range")
        self.slot = slot
        self.ret_buffer = array("B", [0]*self.MAX_IPC_RETURN_SIZE)
        self.ipc_buffer = array("B", [0]*self.MAX_IPC_SIZE)
        self.batch_arg_place = array("I", [0]*self.MAX_BATCH_REPLY_COUNT)
