"""Business logic, kept free of Flask request handling.

Blueprints translate HTTP into calls on these functions and back again. Keeping
the boundary sharp means the optimizer, the carbon model and the metrics
aggregations are all testable without a request context.
"""

from ecoai.services.carbon import CarbonCalculator
from ecoai.services.mailer import Mailer, MailError, Message
from ecoai.services.optimizer import OptimizationResult, PromptOptimizer, Strategy, optimizer

__all__ = [
    "CarbonCalculator",
    "MailError",
    "Mailer",
    "Message",
    "OptimizationResult",
    "PromptOptimizer",
    "Strategy",
    "optimizer",
]
