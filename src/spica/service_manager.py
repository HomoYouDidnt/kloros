import logging
from pathlib import Path
from typing import Optional, Dict, Any
from src.spica.lifecycle import LifecycleStateMachine, LifecycleState
from src.spica.differentiation import DifferentiationRecipe, load_recipe
from src.spica.rpc_server import RPCServer
from src.spica.registry import CapabilityRegistry

logger = logging.getLogger(__name__)

class SPICAServiceManager:
    def __init__(
        self,
        role: str,
        socket_path: str,
        registry_path: Path,
    ):
        self.role = role
        self.socket_path = socket_path

        self.lifecycle = LifecycleStateMachine()
        self.registry = CapabilityRegistry(registry_path)
        self.rpc_server = RPCServer(socket_path)

        self.recipe: Optional[DifferentiationRecipe] = None

        self._register_rpc_methods()

    def _register_rpc_methods(self):
        self.rpc_server.register_method("differentiate", self._handle_rpc_differentiate)
        self.rpc_server.register_method("query_state", self._handle_rpc_query_state)
        self.rpc_server.register_method("reprogram", self._handle_rpc_reprogram)

    def _handle_rpc_differentiate(self, params: Dict[str, Any]) -> Dict[str, Any]:
        recipe_path = params["recipe_path"]
        return self.differentiate(recipe_path)

    def _handle_rpc_query_state(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return self.get_status()

    def _handle_rpc_reprogram(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return self.reprogram()

    def differentiate(self, recipe_path: str) -> Dict[str, Any]:
        try:
            self.lifecycle.transition_to(LifecycleState.PRIMED, metadata={"recipe_path": recipe_path})

            self.recipe = load_recipe(Path(recipe_path))

            self.lifecycle.transition_to(LifecycleState.DIFFERENTIATING)

            self._apply_recipe()

            self.lifecycle.transition_to(LifecycleState.SPECIALIZED)

            capability = self.recipe.spec["target_capability"]
            specialization = self.recipe.spec["specialization"]

            self.registry.register(
                capability=capability,
                specialization=specialization,
                provider=self.role,
                socket=self.socket_path,
                version=self.recipe.metadata["version"],
                state="SPECIALIZED"
            )

            self.lifecycle.transition_to(LifecycleState.INTEGRATED)

            self.registry.update_state(self.role, "INTEGRATED")

            logger.info(f"SPICA {self.role} differentiated to {capability}/{specialization}")

            return {
                "success": True,
                "capability": capability,
                "specialization": specialization,
                "state": self.lifecycle.current_state.value
            }

        except Exception as e:
            logger.error(f"Differentiation failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def _apply_recipe(self):
        pass

    def reprogram(self) -> Dict[str, Any]:
        try:
            if self.recipe:
                capability = self.recipe.spec["target_capability"]
                specialization = self.recipe.spec["specialization"]

                self.registry.deregister(self.role)

            self.lifecycle.reprogram()
            self.recipe = None

            logger.info(f"SPICA {self.role} reprogrammed to PLURIPOTENT")

            return {
                "success": True,
                "state": self.lifecycle.current_state.value
            }

        except Exception as e:
            logger.error(f"Reprogram failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def get_status(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "state": self.lifecycle.current_state.value,
            "recipe": self.recipe.metadata["name"] if self.recipe else None,
            "socket": self.socket_path
        }

    def start(self):
        self.rpc_server.start()
        logger.info(f"SPICA service {self.role} started")

    def stop(self):
        if self.recipe and self.lifecycle.current_state == LifecycleState.INTEGRATED:
            try:
                self.registry.deregister(self.role)
            except Exception as e:
                logger.warning(f"Failed to deregister on stop: {e}")

        self.rpc_server.stop()
        logger.info(f"SPICA service {self.role} stopped")
