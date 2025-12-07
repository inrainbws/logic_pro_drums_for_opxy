#!/usr/bin/env python3
"""
Generate MIDI file to trigger Logic Pro drum kit samples.

This script creates a MIDI file that plays 24 drum notes sequentially,
with enough spacing between notes for cymbal tails to decay.

Usage:
    python generate_drum_midi.py [output.mid] [--spacing SECONDS] [--velocity VALUE]

Requirements:
    pip install mido
"""

import argparse
import json
from pathlib import Path

try:
    import mido
    from mido import MidiFile, MidiTrack, Message, MetaMessage
except ImportError:
    print("Error: mido library required. Install with: pip install mido")
    exit(1)


# Default mapping file path (same directory as script)
DEFAULT_MAPPING_FILE = Path(__file__).parent / "logic_drum_mapping_standard.json"


def get_duration_for_sound(name: str) -> float:
    """Determine appropriate duration based on sound type."""
    name_lower = name.lower()

    # Cymbals need long decay
    if any(word in name_lower for word in ['crash', 'china', 'splash']):
        return 5.0
    if any(word in name_lower for word in ['ride', 'cymbal']):
        return 4.0

    # Hi-hats
    if 'open' in name_lower and 'hat' in name_lower:
        return 3.0
    if 'hat' in name_lower:
        return 2.0

    # Toms
    if 'tom' in name_lower or 'floor' in name_lower:
        return 2.5

    # Short percussion
    if any(word in name_lower for word in ['kick', 'snare', 'clap', 'stick', 'cowbell', 'claves']):
        return 2.0

    # Sustained percussion
    if any(word in name_lower for word in ['tambourine', 'shaker', 'vibraslap']):
        return 2.5

    # Default
    return 2.0


def load_drum_mapping(mapping_file: Path) -> list[tuple[int, str, float]]:
    """
    Load drum mapping from JSON file and add durations.

    Supports two formats:
    1. Array format (preferred for OP-XY compatibility):
       [{"note": 36, "name": "Kick"}, ...]
       Order is preserved - index determines OP-XY slot.

    2. Object format (legacy):
       {"36": "Kick", ...}
       Sorted by MIDI note number.
    """
    with open(mapping_file, 'r') as f:
        mapping = json.load(f)

    drum_list = []

    if isinstance(mapping, list):
        # Array format - preserve order for OP-XY slot compatibility
        for item in mapping:
            note = item["note"]
            name = item["name"]
            duration = get_duration_for_sound(name)
            drum_list.append((note, name, duration))
    else:
        # Object format - sort by MIDI note
        for note_str, name in mapping.items():
            note = int(note_str)
            duration = get_duration_for_sound(name)
            drum_list.append((note, name, duration))
        drum_list.sort(key=lambda x: x[0])

    return drum_list


def generate_drum_midi(
    output_path: str = "drum_trigger.mid",
    spacing_multiplier: float = 1.0,
    velocity: int = 127,
    bpm: int = 120,
    mapping_file: Path = DEFAULT_MAPPING_FILE,
):
    """
    Generate a MIDI file that triggers each drum sample sequentially.

    Args:
        output_path: Output MIDI file path
        spacing_multiplier: Multiply default spacing (1.0 = default, 2.0 = double)
        velocity: Note velocity (0-127)
        bpm: Tempo in beats per minute
        mapping_file: Path to JSON file with drum mapping
    """
    # Load drum mapping from JSON
    drum_mapping = load_drum_mapping(mapping_file)
    print(f"Loaded {len(drum_mapping)} drums from {mapping_file.name}")

    mid = MidiFile(type=0)  # Type 0 = single track
    track = MidiTrack()
    mid.tracks.append(track)

    # Set tempo
    tempo = mido.bpm2tempo(bpm)
    track.append(MetaMessage('set_tempo', tempo=tempo))

    # Set track name
    track.append(MetaMessage('track_name', name='Logic Drum Export'))

    # Calculate ticks per beat (default is 480)
    ticks_per_beat = mid.ticks_per_beat

    print(f"Generating MIDI file: {output_path}")
    print(f"Tempo: {bpm} BPM, Velocity: {velocity}")
    print(f"Ticks per beat: {ticks_per_beat}")
    print("-" * 50)

    current_time = 0

    # Add a short lead-in (1 beat of silence)
    lead_in_ticks = ticks_per_beat

    for i, (note, name, base_duration) in enumerate(drum_mapping):
        # Calculate spacing in ticks
        duration_seconds = base_duration * spacing_multiplier
        duration_beats = duration_seconds * (bpm / 60)
        duration_ticks = int(duration_beats * ticks_per_beat)

        # Delta time for this note (time since last event)
        if i == 0:
            delta = lead_in_ticks
        else:
            delta = 0  # Note-on happens right after previous note-off

        # Note on
        track.append(Message('note_on', note=note, velocity=velocity, time=delta))

        # Note off (short note - let Logic's sample play out naturally)
        note_length_ticks = int(0.1 * (bpm / 60) * ticks_per_beat)  # 100ms note
        track.append(Message('note_off', note=note, velocity=0, time=note_length_ticks))

        # Add remaining spacing
        remaining_ticks = duration_ticks - note_length_ticks
        if remaining_ticks > 0:
            # Add a dummy controller message to hold the time
            # Actually, we'll just account for this in the next note's delta
            pass

        current_time += duration_seconds

        print(f"  [{i+1:2d}] Note {note:3d} ({name:20s}) @ {current_time - duration_seconds:.1f}s, duration: {duration_seconds:.1f}s")

    # Recalculate with proper timing
    track.clear()
    track.append(MetaMessage('set_tempo', tempo=tempo))
    track.append(MetaMessage('track_name', name='Logic Drum Export'))

    cumulative_ticks = lead_in_ticks

    for i, (note, name, base_duration) in enumerate(drum_mapping):
        duration_seconds = base_duration * spacing_multiplier
        duration_beats = duration_seconds * (bpm / 60)
        duration_ticks = int(duration_beats * ticks_per_beat)
        note_length_ticks = int(0.1 * (bpm / 60) * ticks_per_beat)

        if i == 0:
            track.append(Message('note_on', note=note, velocity=velocity, time=lead_in_ticks))
        else:
            track.append(Message('note_on', note=note, velocity=velocity, time=0))

        track.append(Message('note_off', note=note, velocity=0, time=note_length_ticks))

        # Spacing until next note
        spacing_ticks = duration_ticks - note_length_ticks
        if i < len(drum_mapping) - 1:
            # Add spacing as delta time on next note
            track.append(Message('note_on', note=0, velocity=0, time=spacing_ticks))
            track.append(Message('note_off', note=0, velocity=0, time=0))

    # Final cleanup - simpler approach
    track.clear()
    track.append(MetaMessage('set_tempo', tempo=tempo))
    track.append(MetaMessage('track_name', name='Logic Drum Export'))

    last_tick = 0
    events = []

    # Build event list with absolute times
    current_tick = lead_in_ticks
    for i, (note, name, base_duration) in enumerate(drum_mapping):
        duration_seconds = base_duration * spacing_multiplier
        duration_beats = duration_seconds * (bpm / 60)
        duration_ticks = int(duration_beats * ticks_per_beat)
        note_length_ticks = int(0.1 * (bpm / 60) * ticks_per_beat)

        events.append((current_tick, 'note_on', note, velocity))
        events.append((current_tick + note_length_ticks, 'note_off', note, 0))

        current_tick += duration_ticks

    # Sort events by time
    events.sort(key=lambda x: (x[0], 0 if x[1] == 'note_off' else 1))

    # Convert to delta times
    last_tick = 0
    for tick, msg_type, note, vel in events:
        delta = tick - last_tick
        if msg_type == 'note_on':
            track.append(Message('note_on', note=note, velocity=vel, time=delta))
        else:
            track.append(Message('note_off', note=note, velocity=vel, time=delta))
        last_tick = tick

    # End of track
    track.append(MetaMessage('end_of_track', time=ticks_per_beat))

    # Save file
    mid.save(output_path)

    total_duration = sum(d * spacing_multiplier for _, _, d in drum_mapping) + 1
    print("-" * 50)
    print(f"Total duration: ~{total_duration:.1f} seconds")
    print(f"Saved: {output_path}")
    print(f"\nNext steps:")
    print(f"  1. Import {output_path} into Logic Pro")
    print(f"  2. Route to Drum Kit Designer track")
    print(f"  3. Bounce/export as audio (WAV, 44100 Hz, 16-bit)")
    print(f"  4. Run splice_and_export.py on the bounced audio")

    # Save timing info for slicer
    timing_file = Path(output_path).with_suffix('.timing.txt')
    with open(timing_file, 'w') as f:
        f.write(f"# Drum trigger timing info\n")
        f.write(f"# BPM: {bpm}\n")
        f.write(f"# Spacing multiplier: {spacing_multiplier}\n")
        f.write(f"# Format: index, midi_note, name, start_time_sec, duration_sec\n")

        current_time = 1.0 * (60 / bpm)  # Lead-in
        for i, (note, name, base_duration) in enumerate(drum_mapping):
            duration = base_duration * spacing_multiplier
            f.write(f"{i},{note},{name},{current_time:.4f},{duration:.4f}\n")
            current_time += duration

    print(f"Timing info saved: {timing_file}")

    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Generate MIDI file to trigger Logic Pro drum samples"
    )
    parser.add_argument(
        "output",
        nargs="?",
        default="drum_trigger.mid",
        help="Output MIDI file path (default: drum_trigger.mid)"
    )
    parser.add_argument(
        "--spacing",
        type=float,
        default=1.0,
        help="Spacing multiplier (1.0 = default, 2.0 = double spacing)"
    )
    parser.add_argument(
        "--velocity",
        type=int,
        default=127,
        help="Note velocity 0-127 (default: 127)"
    )
    parser.add_argument(
        "--bpm",
        type=int,
        default=120,
        help="Tempo in BPM (default: 120)"
    )
    parser.add_argument(
        "--mapping",
        type=Path,
        default=DEFAULT_MAPPING_FILE,
        help=f"Path to drum mapping JSON file (default: {DEFAULT_MAPPING_FILE.name})"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List drum mapping and exit"
    )

    args = parser.parse_args()

    # Check mapping file exists
    if not args.mapping.exists():
        print(f"Error: Mapping file not found: {args.mapping}")
        exit(1)

    if args.list:
        drum_mapping = load_drum_mapping(args.mapping)
        print(f"Drum Mapping ({len(drum_mapping)} samples from {args.mapping.name}):")
        print("-" * 70)
        print(f"  {'Slot':<5} {'OP-XY':<6} {'Logic':<6} {'Name':<28} {'Duration'}")
        print("-" * 70)
        for i, (note, name, duration) in enumerate(drum_mapping):
            opxy_note = 53 + i  # OP-XY slots start at F#3 (53)
            print(f"  {i:<5} {opxy_note:<6} {note:<6} {name:<28} {duration:.1f}s")
        return

    generate_drum_midi(
        output_path=args.output,
        spacing_multiplier=args.spacing,
        velocity=args.velocity,
        bpm=args.bpm,
        mapping_file=args.mapping
    )


if __name__ == "__main__":
    main()
