"""The driver conformance suite (Task 3f.1, target architecture §4 U2 and G7).

Every `AgentDriver` passes the same cases on the same host inputs. A case is driver-neutral:
it drives a `Subject` through a small host (`world.Host`) that executes reads on synthetic
fixture data and builds context packs with the kernel's assembler, and it checks what the
driver returns, what it persists and, for a driver with a model, what the model received.

A driver joins the suite through a `DriverAdapter` (see `adapters`): it maps each scenario a
case names to that driver's recorded or scripted input, and it declares every case that does
not apply to it, with the reason. Nothing is skipped silently: a case the adapter does not
declare runs, and a missing scenario or model view fails it.
"""

from .cases import CASES, TOPICS, Case
from .harness import DriverAdapter, ModelView, NoModel, Subject

__all__ = ["CASES", "TOPICS", "Case", "DriverAdapter", "ModelView", "NoModel", "Subject"]
