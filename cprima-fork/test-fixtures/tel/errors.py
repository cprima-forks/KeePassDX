"""The system exceptions of the UI test: problems of the phone, the app or the screen reading, never a
verdict on the app. They live here so that the device layer and the object repository can both use them.
"""


class SystemException(Exception):
    """Infrastructure problem: the phone, the app or the screen reading is not in a state the test can
    work with. It is not a verdict on the app. The runner recovers and retries once, then reports an
    error (never a pass or a fail)."""


class DeviceError(SystemException):
    """The phone is not in the state the test expects."""


class Locked(DeviceError):
    """KeePassDX shows its unlock screen. The runner re-initialises through the setup, which unlocks
    the fixture database with its documented test password; no person is needed."""


class NeedsPerson(DeviceError):
    """A handover: only a person can go on (a modal that nobody told the script how to answer is
    showing). It is not a failure and no attempt is used up: the runner pauses, says what it needs,
    waits until the phone shows the person has acted, and resumes from a clean slate. Only a handover
    that nobody resolves in time ends the run."""


class UnknownModal(NeedsPerson):
    """A modal that the table of known dialogs does not cover."""


class WaitTimeout(DeviceError):
    """A condition did not come true in time; the message says what was waited for and what the
    phone showed."""


class ScreenshotFailed(SystemException):
    """A screenshot is missing or black. For a test whose product is evidence this is a system
    exception that fails fast: the usual cause is a secure window, which KeePassDX produces unless its
    "Screenshot mode" setting is on. A run does not go on without its evidence."""


class WrongState(DeviceError):
    """The phone is not in the screen the action needs (the app is behind something, in another
    screen, or a gesture did not reach it). A system exception: recovery, then a repeat."""


class BusinessException(Exception):
    """A problem with the process or its data, not with the phone: for example the entry on the phone
    does not hold what the spec says, or a title is not in the database. It is caught before the
    system exceptions, it is never repeated (a repeat would read the same wrong data), and it is
    reported as an error with the cause "data"."""


class DataMismatch(BusinessException):
    """The fixture on the phone differs from the spec or the file."""


class ElementMissing(WrongState):
    """An element of the object repository is not on the screen. The message names the element and the
    screen it belongs to, so a changed app shows up as one named failure."""
