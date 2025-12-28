
import sqlite3
import datetime

def analyze_performance(db_path="ml_data.db"):
    print(f"--- ⏱ ANALYSIS OF BOT PERFORMANCE ({db_path}) ---")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT timestamp, state_before, action FROM ml_transitions ORDER BY id ASC")
        rows = cursor.fetchall()
        conn.close()
    except Exception as e:
        print(f"Error reading DB: {e}")
        return

    if not rows:
        print("⚠ No data found in ml_transitions. Run the bot for a while to generate data.")
        return

    # Helper to parse isoformat
    def parse_ts(t_str):
        try:
            return datetime.datetime.fromisoformat(t_str)
        except:
            return None

    durations = []
    transitions = {} # Key: "State->Action", Value: [list of durations]

    prev_ts = None
    
    for row in rows:
        ts_str, state, action = row
        curr_ts = parse_ts(ts_str)
        
        if prev_ts and curr_ts:
            delta = (curr_ts - prev_ts).total_seconds()
            
            # Filter huge gaps (bot paused, or long ad)
            if delta < 15.0: 
                durations.append(delta)
                
                key = f"{state} -> [{action}]"
                if key not in transitions:
                    transitions[key] = []
                transitions[key].append(delta)
        
        prev_ts = curr_ts

    if not durations:
        print("Not enough contiguous data to analyze.")
        return

    avg_step = sum(durations) / len(durations)
    durations.sort()
    median_step = durations[len(durations)//2]

    print(f"\n📊 GLOBAL METRICS:")
    print(f"  - Total Recorded Steps: {len(rows)}")
    print(f"  - Average Loop Cycle Time: {avg_step:.3f} seconds")
    print(f"  - Median Loop Cycle Time:  {median_step:.3f} seconds")

    print("\n🐌 AVG DELAY BY ACTION TYPE (Top Slowest):")
    # Average per transition type
    avg_transitions = []
    for key, times in transitions.items():
        avg = sum(times) / len(times)
        avg_transitions.append((avg, key, len(times)))
    
    # Sort by avg desc
    avg_transitions.sort(key=lambda x: x[0], reverse=True)
    
    for avg, key, count in avg_transitions[:10]:
        print(f"  - {key}: {avg:.3f} s (samples: {count})")

    print("\n✅ INTERPRETATION:")
    print(f"  The 'Loop Cycle Time' represents the gap between two decision cycles.")
    if avg_step > 1.5:
        print("  -> > 1.5s: Indicates 'sleep()' calls are dominating the loop.")
    elif avg_step < 0.5:
        print("  -> < 0.5s: Very fast loop (good).")
    else:
        print("  -> 0.5s - 1.5s: Normal operation.")

if __name__ == "__main__":
    analyze_performance()
