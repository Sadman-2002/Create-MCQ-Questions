 (cd "$(git rev-parse --show-toplevel)" && git apply --3way <<'EOF' 
diff --git a/cmd_adventure.py b/cmd_adventure.py
new file mode 100644
index 0000000000000000000000000000000000000000..c9660f4dc9bd90b52be7afa492f71f49f3fa37d1
--- /dev/null
+++ b/cmd_adventure.py
@@ -0,0 +1,329 @@
+"""Command-line adventure game.
+
+This module implements a self-contained text adventure that can be played in
+any command prompt.  The game is intentionally compact so that it can be
+embedded in small projects or used as a starting point for more elaborate
+stories.
+"""
+
+from __future__ import annotations
+
+import argparse
+import textwrap
+from dataclasses import dataclass, field
+from typing import Dict, Iterable, Iterator, List, Optional
+
+
+def wrap(text: str) -> str:
+    """Return ``text`` wrapped to a sensible width for terminals."""
+
+    return textwrap.fill(text, width=78)
+
+
+@dataclass
+class Room:
+    """Representation of a location in the game world."""
+
+    name: str
+    description: str
+    exits: Dict[str, str]
+    items: List[str] = field(default_factory=list)
+    searchable: bool = False
+    searched: bool = False
+
+    def describe(self) -> str:
+        """Return a descriptive string including visible items and exits."""
+
+        details = [wrap(self.description)]
+        if self.items:
+            item_line = "You spot " + ", ".join(f"a {item}" for item in self.items) + "."
+            details.append(wrap(item_line))
+        if self.exits:
+            exits = ", ".join(sorted(self.exits))
+            details.append(wrap(f"Exits lead: {exits}."))
+        return "\n".join(details)
+
+
+class Game:
+    """Encapsulates the adventure logic and command handling."""
+
+    def __init__(self) -> None:
+        self.rooms: Dict[str, Room] = self._build_world()
+        self.current_room: Room = self.rooms["courtyard"]
+        self.inventory: List[str] = []
+        self.victory: bool = False
+
+    def _build_world(self) -> Dict[str, Room]:
+        """Return the dictionary of rooms that make up the world."""
+
+        return {
+            "courtyard": Room(
+                name="Abandoned Courtyard",
+                description=(
+                    "Moonlight filters through the clouds, revealing the cracked stone"
+                    " courtyard of an ancient academy. Vines creep along the walls and"
+                    " an iron gate looms to the north."
+                ),
+                exits={"north": "gate", "east": "library", "west": "dormitory"},
+            ),
+            "library": Room(
+                name="Forgotten Library",
+                description=(
+                    "Dusty shelves line the walls, and countless tomes lie in ruin."
+                    " A lectern holds a leather-bound journal that has miraculously"
+                    " survived the years."
+                ),
+                exits={"west": "courtyard"},
+                items=["journal"],
+            ),
+            "dormitory": Room(
+                name="Dormitory Ruins",
+                description=(
+                    "Collapsed bunks and shattered trunks suggest the students fled"
+                    " in a hurry. Amid the debris, a glint catches your eye near a"
+                    " toppled wardrobe."
+                ),
+                exits={"east": "courtyard", "south": "workshop"},
+                searchable=True,
+            ),
+            "workshop": Room(
+                name="Arcane Workshop",
+                description=(
+                    "A chalk circle occupies the center of the room, and a workbench"
+                    " is scattered with gears and crystals. The air hums with latent"
+                    " energy."
+                ),
+                exits={"north": "dormitory"},
+                items=["charged crystal"],
+            ),
+            "gate": Room(
+                name="Sealed Gate",
+                description=(
+                    "An imposing gate bars the way out. A weathered inscription reads,"
+                    " 'Only those who remember our oath may pass.'"
+                ),
+                exits={"south": "courtyard"},
+            ),
+        }
+
+    # --- Player messaging helpers -------------------------------------------------
+    def _print_header(self, text: str) -> None:
+        border = "=" * len(text)
+        print(f"\n{border}\n{text}\n{border}\n")
+
+    def _print(self, text: str) -> None:
+        print(wrap(text))
+
+    # --- Core gameplay ------------------------------------------------------------
+    def introduce(self) -> None:
+        self._print_header("Echoes of BUP")
+        intro = (
+            "You are a historian investigating the abandoned campus of the"
+            " Bangladesh University of Professionals. Legends whisper that the"
+            " founders sealed away their greatest secret behind an oath only true"
+            " scholars can recall. Explore the ruins, uncover their ritual, and"
+            " escape before the night ends."
+        )
+        self._print(intro)
+        self._print("Type 'help' for a list of commands.")
+        print()
+        self.look()
+
+    def look(self) -> None:
+        self._print_header(self.current_room.name)
+        print(self.current_room.describe())
+
+    def inventory_list(self) -> None:
+        if not self.inventory:
+            self._print("Your satchel is empty.")
+            return
+        self._print("You are carrying: " + ", ".join(self.inventory) + ".")
+
+    def search(self) -> None:
+        room = self.current_room
+        if not room.searchable:
+            self._print("You find nothing new here.")
+            return
+        if room.searched:
+            self._print("You already rifled through this area.")
+            return
+        room.searched = True
+        room.items.append("ancient key")
+        self._print(
+            "Beneath the debris you uncover a sealed lockbox. Inside, wrapped in"
+            " cloth, rests an ancient key."
+        )
+
+    def take(self, item: str) -> None:
+        room = self.current_room
+        if item not in room.items:
+            self._print(f"There is no {item} here.")
+            return
+        room.items.remove(item)
+        self.inventory.append(item)
+        self._print(f"You carefully take the {item}.")
+
+    def move(self, direction: str) -> None:
+        room = self.current_room
+        direction = direction.lower()
+        if direction not in room.exits:
+            self._print("You bump into a wall. That way is blocked.")
+            return
+        destination_key = room.exits[direction]
+        self.current_room = self.rooms[destination_key]
+        self.look()
+
+    def use(self, item: str) -> None:
+        if item not in self.inventory:
+            self._print(f"You are not carrying a {item}.")
+            return
+        if item == "journal":
+            self._print(
+                "The journal recounts the founders' oath: 'Knowledge, Duty,"
+                " Patriotism.' The words resonate with power."
+            )
+            return
+        if item == "charged crystal" and self.current_room.name == "Arcane Workshop":
+            self._print(
+                "You set the crystal onto the workbench. It hums softly, recharging"
+                " your lantern and revealing hidden inscriptions in the room."
+            )
+            return
+        if item == "ancient key" and self.current_room.name == "Sealed Gate":
+            self._print(
+                "The key fits perfectly. As the gate unlocks, you speak the oath"
+                " learned from the journal. The iron bars swing open, and a warm"
+                " breeze greets you. You have escaped!"
+            )
+            self.victory = True
+            return
+        self._print("Using that here accomplishes nothing obvious.")
+
+    # --- Command parsing ----------------------------------------------------------
+    def process_command(self, command: str) -> bool:
+        """Handle a single player command.
+
+        Returns ``True`` to continue playing, or ``False`` to exit the game loop.
+        """
+
+        command = command.strip()
+        if not command:
+            return True
+        verb, *args = command.split()
+        verb = verb.lower()
+        argument = " ".join(args)
+
+        if verb in {"quit", "exit"}:
+            self._print("You retreat from the ruins, vowing to return another night.")
+            return False
+        if verb == "help":
+            self._print(
+                "Commands: look, go <direction>, take <item>, search, inventory,"
+                " use <item>, read <item>, help, quit"
+            )
+            return True
+        if verb == "look":
+            self.look()
+            return True
+        if verb in {"go", "move"}:
+            if not argument:
+                self._print("Go where?")
+            else:
+                self.move(argument)
+            return True
+        if verb == "inventory":
+            self.inventory_list()
+            return True
+        if verb == "search":
+            self.search()
+            return True
+        if verb in {"take", "grab"}:
+            if not argument:
+                self._print("Take what?")
+            else:
+                self.take(argument)
+            return True
+        if verb in {"use", "read"}:
+            if not argument:
+                self._print("Use what?")
+            else:
+                self.use(argument)
+            return True
+
+        self._print("Your words echo unanswered. Try a different command.")
+        return True
+
+    # --- Game loop ----------------------------------------------------------------
+    def play(self, commands: Optional[Iterable[str]] = None) -> None:
+        """Run the main game loop.
+
+        The optional ``commands`` iterable makes it easy to script playthroughs
+        for demonstrations or tests. When omitted the game falls back to
+        interactive input via ``input``.
+        """
+
+        self.introduce()
+        iterator: Optional[Iterator[str]] = iter(commands) if commands is not None else None
+        while not self.victory:
+            if iterator is None:
+                try:
+                    command = input("> ")
+                except EOFError:
+                    print()
+                    break
+            else:
+                try:
+                    command = next(iterator)
+                except StopIteration:
+                    break
+                print(f"> {command}")
+            if not self.process_command(command):
+                break
+            if self.victory:
+                break
+        if self.victory:
+            self._print_header("Victory")
+            self._print(
+                "Congratulations! You uncovered the founders' secret and escaped"
+                " the ruins with your discoveries."
+            )
+
+
+def scripted_playthrough() -> Iterable[str]:
+    """Return a sequence of commands that solves the game."""
+
+    return [
+        "look",
+        "go west",
+        "search",
+        "take ancient key",
+        "go south",
+        "take charged crystal",
+        "go north",
+        "go east",
+        "go east",
+        "take journal",
+        "read journal",
+        "go west",
+        "go north",
+        "use ancient key",
+    ]
+
+
+def main(argv: Optional[List[str]] = None) -> int:
+    parser = argparse.ArgumentParser(description="Play a command-line adventure.")
+    parser.add_argument(
+        "--demo",
+        action="store_true",
+        help="run a non-interactive playthrough demonstrating the solution",
+    )
+    args = parser.parse_args(argv)
+
+    game = Game()
+    commands = scripted_playthrough() if args.demo else None
+    game.play(commands=commands)
+    return 0
+
+
+if __name__ == "__main__":
+    raise SystemExit(main()) 
EOF
)