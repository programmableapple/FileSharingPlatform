import sys
import traceback

def run_client():
    try:
        # Import and run the client
        from client import FileClientGUI
        import tkinter as tk
        
        root = tk.Tk()
        app = FileClientGUI(root)
        root.mainloop()
    except Exception as e:
        # Print the error and traceback
        print(f"Error: {e}")
        print("\nTraceback:")
        traceback.print_exc()
        
        # Keep the console window open
        print("\nPress Enter to exit...")
        input()
        sys.exit(1)

if __name__ == "__main__":
    run_client()
