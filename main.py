#!/usr/bin/env python3
import os
import sys
import subprocess

def clear_screen():
    """Clear the console screen."""
    os.system('cls' if os.name == 'nt' else 'clear')

def print_header():
    """Print the application header."""
    clear_screen()
    print("=" * 50)
    print("SOCIAL MEDIA SCRAPER".center(50))
    print("=" * 50)
    print("\nSelect a platform to scrape:")

def run_instagram_scraper():
    """Run the Instagram scraper."""
    try:
        script_path = os.path.join(os.path.dirname(__file__), 'Instagram', 'insta.py')
        subprocess.run([sys.executable, script_path], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running Instagram scraper: {e}")
        input("\nPress Enter to continue...")
    except FileNotFoundError:
        print("Instagram scraper not found. Please ensure the 'Instagram' directory exists.")
        input("\nPress Enter to continue...")

def main():
    """Main function to run the application."""
    while True:
        print_header()
        print("1. Instagram")
        print("2. Facebook (Coming Soon)")
        print("0. Exit")
        
        choice = input("\nEnter your choice (0-2): ").strip()
        
        if choice == '1':
            run_instagram_scraper()
        elif choice == '2':
            print("\nFacebook scraper is not yet implemented.")
            input("Press Enter to continue...")
        elif choice == '0':
            print("\nThank you for using Social Media Scraper!")
            break
        else:
            print("\nInvalid choice. Please try again.")
            input("Press Enter to continue...")

if __name__ == "__main__":
    main()
