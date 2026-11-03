"""Who may send documents: phone -> driver -> cab. An unknown number gets a "not registered" reply and nothing is
stored. A live deployment loads this from a private store; the repo carries only synthetic examples. An entry
without "synthetic": true counts as real, so it can never reach a model hosted outside India by accident."""
import json
import re
from dataclasses import dataclass

from .logs import hid
from .rules import norm_vehicle


def norm_phone(p) -> str:
    digits = re.sub(r"\D", "", str(p or ""))
    if len(digits) == 10:
        digits = "91" + digits
    return "+" + digits if digits else ""


@dataclass(frozen=True)
class Driver:
    phone: str
    driver_name: str
    vehicle_no: str
    cab_id: str
    language: str = "en"
    owner_names: tuple = ()
    synthetic: bool = False
    training_token: str = ""        # the driver's learner token on the training platform; empty = no Train link


class Registry:
    def __init__(self, entries, client: str = ""):
        self.client = client
        self._by_phone, self._by_id = {}, {}
        for e in entries:
            d = Driver(phone=norm_phone(e["phone"]), driver_name=e.get("driver_name", ""),
                       vehicle_no=norm_vehicle(e["vehicle_no"]), cab_id=e.get("cab_id", ""),
                       language=e.get("language", "en"), owner_names=tuple(e.get("owner_names", [])),
                       synthetic=bool(e.get("synthetic", False)), training_token=str(e.get("training_token") or ""))
            self._by_phone[d.phone] = d
            self._by_id[hid(d.phone)] = d

    @classmethod
    def from_file(cls, path: str) -> "Registry":
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return cls(data["drivers"], data.get("client", ""))

    def lookup(self, phone) -> Driver | None:
        return self._by_phone.get(norm_phone(phone))

    def by_id(self, sender_id: str) -> Driver | None:
        """Look a driver up by hid(phone), so queued jobs never carry a raw phone number."""
        return self._by_id.get(sender_id)

    def drivers(self) -> list:
        return list(self._by_phone.values())
