import argparse
import yaml

from pathlib import Path


def load_config(config_path: Path) -> dict:
    """Load configuration from YAML file."""
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    return config


def print_summary(results: dict, args: argparse.Namespace):
    """Affiche un résumé des données de monitoring collectées."""
    print("\n" + "="*50)
    print("RÉSUMÉ DU MONITORING")
    print("="*50)

    # Section 1: Timing
    loading_time = results.get('loading_time', 0)
    processing_time = results.get('processing_time', 0)
    total_time = results.get('total_time', 0)
    
    print("\n--- Timing Summary ---")
    print(f"Data loading time    : {loading_time:.2f} seconds")
    print(f"Processing time      : {processing_time:.2f} seconds")
    print(f"Total time           : {total_time:.2f} seconds")

    # Section 2: Data loading
    if args.monitor_ram:
        ram_before = results.get('ram_before_load', 0)
        ram_after = results.get('ram_after_load', 0)
        print("\n--- Loading Phase ---")
        print(f"RAM before loading : {ram_before:.2f} Mo")
        print(f"RAM after loading  : {ram_after:.2f} Mo")
        print(f"Delta                 : {ram_after - ram_before:+.2f} Mo")

        # Section 3: Boucle de traitement des événements
        loop_data = results.get('ram_during_loop', [])
        print("\n--- Phase de Traitement (Boucle) ---")
        if not loop_data:
            print("No RAM data was collected during the loop.")
        else:
            num_samples = len(loop_data)
            # Extraire les valeurs de RAM
            ram_values = [ram for idx, ram in loop_data]
            
            print(f"Number of RAM samples taken : {num_samples}")
            print(f"RAM at the beginning of the loop        : {ram_values[0]:.2f} Mo (event #{loop_data[0][0]})")
            print(f"RAM maximale atteinte            : {max(ram_values):.2f} Mo")
            print(f"RAM at the end of the loop          : {ram_values[-1]:.2f} Mo (event #{loop_data[-1][0]})")

    print("\n" + "="*50)


