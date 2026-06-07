from bus_persistencia.bus.state_bus import M2_WRITER_ID, StateBus, WriterNotAuthorizedError

UnauthorizedWriterError = WriterNotAuthorizedError

__all__ = [
    "StateBus",
    "WriterNotAuthorizedError",
    "UnauthorizedWriterError",
    "M2_WRITER_ID",
]
