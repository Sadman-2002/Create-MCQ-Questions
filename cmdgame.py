 (cd "$(git rev-parse --show-toplevel)" && git apply --3way <<'EOF' 
diff --git a/cmd_game.py b/cmd_game.py
new file mode 100644
index 0000000000000000000000000000000000000000..76e016618105295cf3322facc45043f2065b8474
--- /dev/null
+++ b/cmd_game.py
@@ -0,0 +1,129 @@
+"""Command-line adventure game.
+
+Run this script in a command prompt to experience a simple text-based
+adventure set on the Bangladesh University of Professionals campus.
+"""
+
+import random
+import textwrap
+
+
+def print_header():
+    banner = "=" * 60
+    title = "WELCOME TO THE BUP CAMPUS QUEST"
+    print(banner)
+    print(title.center(60))
+    print(banner)
+    print()
+
+
+def intro_story():
+    story = (
+        "You are a cadet at Bangladesh University of Professionals preparing for the "
+        "Inter-University Innovation Challenge. \n"
+        "Explore the campus, gather resources, and make the right decisions to ensure your team wins!"
+    )
+    print(textwrap.fill(story, width=70))
+    print()
+
+
+def choose_teammate():
+    teammates = {
+        "Fatima": "A brilliant strategist who never misses a clue.",
+        "Rahim": "A tech wizard with a knack for solving puzzles.",
+        "Tanvir": "An athlete whose energy keeps morale high.",
+    }
+    print("Choose a teammate to accompany you:")
+    for idx, (name, description) in enumerate(teammates.items(), start=1):
+        print(f"  {idx}. {name} - {description}")
+
+    while True:
+        choice = input("Enter the number of your teammate: ").strip()
+        if choice.isdigit():
+            choice_idx = int(choice)
+            if 1 <= choice_idx <= len(teammates):
+                teammate_name = list(teammates.keys())[choice_idx - 1]
+                print(f"Great choice! {teammate_name} joins your team.\n")
+                return teammate_name
+        print("Invalid selection. Please choose a valid teammate number.\n")
+
+
+def campus_challenge(teammate):
+    challenges = [
+        {
+            "location": "Innovation Lab",
+            "prompt": "A prototype drone needs calibration before the judges arrive.",
+            "success": (
+                "You and {teammate} tweak the drone's sensors and achieve perfect stability!"
+            ),
+            "failure": (
+                "The drone sputters and refuses to lift off. Maybe more practice is needed."
+            ),
+        },
+        {
+            "location": "Library",
+            "prompt": "A cryptic research paper holds the final clue to your presentation.",
+            "success": (
+                "Decoding the paper reveals the missing insight. Your presentation is now unbeatable!"
+            ),
+            "failure": (
+                "The dense equations remain a mystery, costing precious time."
+            ),
+        },
+        {
+            "location": "Sports Complex",
+            "prompt": "A quick team-building exercise could boost everyone's morale.",
+            "success": (
+                "The team spirit skyrockets, and everyone is ready to face the judges with confidence!"
+            ),
+            "failure": (
+                "The exercise fizzles, leaving the team a bit unsure of themselves."
+            ),
+        },
+    ]
+
+    random.shuffle(challenges)
+
+    score = 0
+    for challenge in challenges:
+        print(f"You arrive at the {challenge['location']}.")
+        print(textwrap.fill(challenge["prompt"], width=70))
+        decision = input("Do you want to take on this challenge? (yes/no): ").strip().lower()
+        if decision in {"yes", "y"}:
+            success = random.choice([True, False])
+            if success:
+                print(textwrap.fill(challenge["success"].format(teammate=teammate), width=70))
+                score += 1
+            else:
+                print(textwrap.fill(challenge["failure"], width=70))
+        else:
+            print("You decide to conserve energy and move on.\n")
+        print()
+
+    return score
+
+
+def final_result(score):
+    print("Final Results")
+    print("-" * 60)
+    if score == 3:
+        print("Outstanding! Your team wins the Innovation Challenge with a perfect score!")
+    elif score == 2:
+        print("Great job! Your innovative ideas impress the judges and earn second place.")
+    elif score == 1:
+        print("Not bad! You learned valuable lessons for next year's competition.")
+    else:
+        print("The challenge was tough, but perseverance will lead to victory next time.")
+    print("\nThanks for playing the BUP Campus Quest!")
+
+
+def main():
+    print_header()
+    intro_story()
+    teammate = choose_teammate()
+    score = campus_challenge(teammate)
+    final_result(score)
+
+
+if __name__ == "__main__":
+    main() 
EOF
)