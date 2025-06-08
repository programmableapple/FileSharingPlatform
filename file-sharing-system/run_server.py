import sys
import traceback

def run_server():
    try:
        # Import and run the server
        from server import FileServer
        
        server = FileServer()
        print("File Server started. Press Ctrl+C to stop.")
        server.start()
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
    run_server()
