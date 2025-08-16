#!/usr/bin/env python3
import os
import sys
from pathlib import Path

def clear_screen():
    """Clear the terminal screen."""
    os.system('cls' if os.name == 'nt' else 'clear')

def display_menu():
    """Display the main menu and get user choice."""
    clear_screen()
    print("\n" + "="*50)
    print("SOCIAL MEDIA SCRAPER".center(50))
    print("="*50)
    print("\n1. Scrape Instagram Profile")
    print("2. Scrape Facebook Profile")
    print("3. Exit")
    
    while True:
        choice = input("\nEnter your choice (1-3): ").strip()
        if choice in ['1', '2', '3']:
            return choice
        print("[!] Invalid choice. Please enter 1, 2, or 3.")

def run_instagram_scraper():
    """Run the Instagram scraper."""
    clear_screen()
    print("\n" + "="*50)
    print("INSTAGRAM SCRAPER".center(50))
    print("="*50)
    
    try:
        from Instagram import insta
        print("\n[i] Starting Instagram scraper...")
        if hasattr(insta, 'main'):
            output_file = insta.main()
            print("\n" + "="*50)
            print(f"[✓] Scraping complete!")
            # Try to display the correct report path if possible
            if output_file and isinstance(output_file, str) and os.path.exists(output_file):
                print(f"[i] Report saved to: {os.path.abspath(output_file)}")
            else:
                print(f"[i] Report saved to: [see output above]")
            print("="*50)
            input("\nPress Enter to return to the main menu.")
            return True
        else:
            print("\n[!] Error: 'main' function not found in Instagram/insta.py")
            input("\nPress Enter to return to the main menu.")
            return False
    except Exception as e:
        print(f"\n[!] Error: {str(e)}")
        input("\nPress Enter to return to the main menu.")
        return False

def run_facebook_scraper():
    """Run the Facebook scraper."""
    clear_screen()
    print("\n" + "="*50)
    print("FACEBOOK SCRAPER".center(50))
    print("="*50)
    
    try:
        from Facebook.facebook import main as facebook_main
        facebook_main()
        input("\nPress Enter to return to the main menu.")
        return True
    except Exception as e:
        print(f"\n[!] Error: {str(e)}")
        input("\nPress Enter to return to the main menu.")
        return False

def main():
    """Main entry point for the scraper tool."""
    while True:
        choice = display_menu()
        
        if choice == '1':
            run_instagram_scraper()
        elif choice == '2':
            run_facebook_scraper()
        elif choice == '3':
            print("\n[!] Exiting...")
            break
        else:
            print("\n[!] Invalid choice. Please try again.")
            continue
            
    # After each operation, just return to main menu

if __name__ == "__main__":
    # Create 'reports' directory if it doesn't exist at the root level
    if not os.path.exists('reports'):
        os.makedirs('reports')
        
    try:
        main()
    except KeyboardInterrupt:
        print("\n[!] Operation cancelled by user")
    except Exception as e:
        print(f"\n[!] An error occurred: {str(e)}")