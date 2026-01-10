"""Support for EvoCarShare device trackers."""
from __future__ import annotations

import logging

from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.components.device_tracker.const import SourceType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from evocarshare import Vehicle

from .const import (
    CONF_SEARCH_MODE,
    CONF_SEARCH_VALUE,
    CONF_TRACKER_ID,
    COORD,
    DOMAIN,
    SEARCH_MODE_COUNT,
    SEARCH_MODE_RADIUS,
)
from .coordinator import EvoCarShareUpdateCoordinator
from .helpers import get_location

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up EvoCarShare device tracker from config entry."""

    coordinator: EvoCarShareUpdateCoordinator = hass.data[DOMAIN][COORD]

    if CONF_TRACKER_ID not in entry.data:
        return

    mode = entry.data.get(CONF_SEARCH_MODE, SEARCH_MODE_COUNT)

    if mode == SEARCH_MODE_COUNT:
        # Create fixed number of entities
        count = entry.data.get(CONF_SEARCH_VALUE, 5)
        entities = []
        for i in range(1, count + 1):
            entities.append(EvoVehicleTracker(coordinator, entry, i))
        async_add_entities(entities)

    elif mode == SEARCH_MODE_RADIUS:
        manager = EvoDynamicTrackerManager(hass, coordinator, entry, async_add_entities)
        entry.async_on_unload(coordinator.async_add_listener(manager.update_entities))
        manager.update_entities()


class EvoVehicleTracker(CoordinatorEntity, TrackerEntity):
    """Representation of an Evo Vehicle Device Tracker (Slot based)."""

    def __init__(
        self,
        coordinator: EvoCarShareUpdateCoordinator,
        entry: ConfigEntry,
        index: int,
    ) -> None:
        super().__init__(coordinator)
        self.config_entry = entry
        self._index = index  # 1-based index
        self._attr_unique_id = f"{entry.entry_id}_evo_{index}"
        self._attr_name = f"Evo {index} ({entry.title})"
        self._vehicle: Vehicle | None = None
        self._distance: float | None = None

    @property
    def source_type(self) -> SourceType:
        """Return the source type, eg gps or router, of the device."""
        return SourceType.GPS

    @property
    def latitude(self) -> float | None:
        """Return latitude value of the device."""
        if self._vehicle:
            return self._vehicle.location.latitude
        return None

    @property
    def longitude(self) -> float | None:
        """Return longitude value of the device."""
        if self._vehicle:
            return self._vehicle.location.longitude
        return None

    @property
    def location_accuracy(self) -> int:
        """Return the location accuracy of the device.
        Value in meters.
        """
        return 0

    @property
    def extra_state_attributes(self) -> dict[str, any]:
        """Return the state attributes."""
        if self._vehicle:
            return {
                "address": self._vehicle.address,
                "plate": self._vehicle.plate,
                "fuel": self._vehicle.fuel,
                "distance": self._distance
            }
        return {}

    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend."""
        return "mdi:car"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        data = self.coordinator.data
        if not data:
            self._vehicle = None
            self._distance = None
            self.async_write_ha_state()
            return

        target_location = get_location(self.hass, self.config_entry.data)
        if not target_location:
            self._vehicle = None
            self._distance = None
            self.async_write_ha_state()
            return

        # Calculate distances locally without modifying shared vehicle objects
        vehicles_with_dist = []
        for v in data:
            dist = v.location.distanceTo(target_location)
            vehicles_with_dist.append((v, dist))

        # Sort by distance
        vehicles_with_dist.sort(key=lambda x: x[1])

        if len(vehicles_with_dist) >= self._index:
            self._vehicle, self._distance = vehicles_with_dist[self._index - 1]
        else:
            self._vehicle = None
            self._distance = None

        self.async_write_ha_state()


class EvoDynamicTrackerManager:
    """Manages dynamic creation/removal of trackers for Radius mode."""

    def __init__(self, hass, coordinator, entry, async_add_entities):
        self.hass = hass
        self.coordinator = coordinator
        self.entry = entry
        self.async_add_entities = async_add_entities
        self.tracked_vehicles = {} # Map plate -> Entity

    @callback
    def update_entities(self):
        data = self.coordinator.data
        if not data:
            return

        target_location = get_location(self.hass, self.entry.data)
        if not target_location:
            return

        radius = self.entry.data.get(CONF_SEARCH_VALUE, 500)

        # Find vehicles in radius
        vehicles_in_radius = []
        for v in data:
             dist = v.location.distanceTo(target_location)
             if dist <= radius:
                 vehicles_in_radius.append((v, dist))

        # Create entities for new vehicles
        new_entities = []
        active_plates = set()

        for v, dist in vehicles_in_radius:
            active_plates.add(v.plate)
            if v.plate not in self.tracked_vehicles:
                entity = EvoSpecificVehicleTracker(self.coordinator, self.entry, v, dist)
                self.tracked_vehicles[v.plate] = entity
                new_entities.append(entity)
            else:
                # Update existing entity
                self.tracked_vehicles[v.plate].update_vehicle_data(v, dist)

        if new_entities:
            self.async_add_entities(new_entities)

        for plate, entity in self.tracked_vehicles.items():
            if plate not in active_plates:
                entity.set_unavailable()


class EvoSpecificVehicleTracker(CoordinatorEntity, TrackerEntity):
    """Representation of a specific Evo Vehicle (by Plate)."""

    def __init__(
        self,
        coordinator: EvoCarShareUpdateCoordinator,
        entry: ConfigEntry,
        vehicle: Vehicle,
        distance: float,
    ) -> None:
        super().__init__(coordinator)
        self.config_entry = entry
        self._vehicle = vehicle
        self._distance = distance
        self._attr_unique_id = f"{entry.entry_id}_evo_{vehicle.plate}"
        self._attr_name = f"Evo {vehicle.plate}"
        self._is_available = True

    @property
    def source_type(self) -> SourceType:
        return SourceType.GPS

    @property
    def latitude(self) -> float | None:
        if self._is_available and self._vehicle:
            return self._vehicle.location.latitude
        return None

    @property
    def longitude(self) -> float | None:
        if self._is_available and self._vehicle:
            return self._vehicle.location.longitude
        return None

    @property
    def available(self) -> bool:
        return self._is_available and super().available

    @property
    def extra_state_attributes(self) -> dict[str, any]:
        if self._is_available and self._vehicle:
            return {
                "address": self._vehicle.address,
                "plate": self._vehicle.plate,
                "fuel": self._vehicle.fuel,
                "distance": self._distance
            }
        return {}

    @property
    def icon(self) -> str:
        return "mdi:car"

    def update_vehicle_data(self, vehicle: Vehicle, distance: float):
        self._vehicle = vehicle
        self._distance = distance
        self._is_available = True
        self.async_write_ha_state()

    def set_unavailable(self):
        self._is_available = False
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        # Updates are pushed by Manager
        pass
