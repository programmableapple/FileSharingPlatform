import socket
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import json
import os
import hashlib
import logging
import time

# Configure logging
logging.basicConfig(
    filename='client_log.txt',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class FileClient:
    def __init__(self, host='localhost', port=9999):
        self.host = host
        self.port = port
        self.socket = None
        self.connected = False
        self.download_dir = 'downloads'
        
        # Create download directory if it doesn't exist
        if not os.path.exists(self.download_dir):
            os.makedirs(self.download_dir)
        
        logging.info(f"Client initialized to connect to {host}:{port}")
    
    def connect(self):
        """Connect to the server"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            self.connected = True
            logging.info(f"Connected to server at {self.host}:{self.port}")
            return True
        except Exception as e:
            logging.error(f"Connection failed: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from the server"""
        if self.socket:
            self.socket.close()
            self.socket = None
            self.connected = False
            logging.info("Disconnected from server")
    
    def list_files(self):
        """Request list of files from server"""
        if not self.connected:
            logging.error("Not connected to server")
            return None
        
        try:
            # Send LIST command
            command = {'command': 'LIST'}
            self.socket.send(json.dumps(command).encode('utf-8'))
            
            # Receive response
            response_data = self.socket.recv(8192)  # Larger buffer for file lists
            response = json.loads(response_data.decode('utf-8'))
            
            if response.get('status') == 'success':
                logging.info("Received file list from server")
                return response.get('files', [])
            else:
                logging.error(f"Error listing files: {response.get('message')}")
                return None
                
        except Exception as e:
            logging.error(f"Error in list_files: {e}")
            self.disconnect()
            return None
    
    def upload_file(self, file_path, progress_callback=None):
        """Upload a file to the server"""
        if not self.connected:
            logging.error("Not connected to server")
            return False, "Not connected to server"
        
        if not os.path.exists(file_path):
            logging.error(f"File not found: {file_path}")
            return False, "File not found"
        
        try:
            filename = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)
            
            # Calculate file hash
            hash_obj = hashlib.sha256()
            with open(file_path, 'rb') as f:
                while chunk := f.read(4096):
                    hash_obj.update(chunk)
            file_hash = hash_obj.hexdigest()
            
            # Send UPLOAD command
            command = {
                'command': 'UPLOAD',
                'filename': filename,
                'file_size': file_size,
                'file_hash': file_hash
            }
            self.socket.send(json.dumps(command).encode('utf-8'))
            
            # Receive server ready confirmation
            response_data = self.socket.recv(1024)
            response = json.loads(response_data.decode('utf-8'))
        # Removed misplaced and undefined code block
           
            if response.get('status') != 'ready':
                logging.error(f"Server not ready: {response.get('message')}")
                return False, response.get('message', 'Server not ready')
            if response.get('status') == 'exists':
                overwrite = messagebox.askyesno(
                    "File Exists",
                    "Overwrite this file? Yes=overwrite, No=rename"
                )
                action_payload = {'command': 'UPLOAD_ACTION', 'action': 'overwrite' if overwrite else 'rename'}
                self.socket.send(json.dumps(action_payload).encode('utf-8'))
                response_data = self.socket.recv(1024)
                response = json.loads(response_data.decode('utf-8'))
            # Server is ready, send file data
            sent_size = 0
            with open(file_path, 'rb') as f:
                while sent_size < file_size:
                    chunk = f.read(4096)
                    if not chunk:
                        break
                    
                    self.socket.send(chunk)
                    sent_size += len(chunk)
                    
                    # Update progress
                    if progress_callback:
                        progress = (sent_size / file_size) * 100
                        progress_callback(progress)
            
            # Wait for final confirmation
            final_response_data = self.socket.recv(1024)
            final_response = json.loads(final_response_data.decode('utf-8'))
            
            if final_response.get('status') == 'success':
                logging.info(f"File {filename} uploaded successfully")
                return True, final_response.get('message', 'Upload successful')
            else:
                logging.error(f"Upload failed: {final_response.get('message')}")
                return False, final_response.get('message', 'Upload failed')
                
        except Exception as e:
            logging.error(f"Error in upload_file: {e}")
            self.disconnect()
            return False, str(e)
    
    def download_file(self, filename, download_dir=None, progress_callback=None):
        """Download a file from the server"""
        if not self.connected:
            logging.error("Not connected to server")
            return False, "Not connected to server"
        
        try:
            # Send DOWNLOAD command
            command = {
                'command': 'DOWNLOAD',
                'filename': filename
            }
            self.socket.send(json.dumps(command).encode('utf-8'))
            
            # Receive file info
            response_data = self.socket.recv(1024)
            response = json.loads(response_data.decode('utf-8'))
            
            if response.get('status') != 'ready':
                logging.error(f"Server not ready: {response.get('message')}")
                return False, response.get('message', 'File not found')
            
            file_size = response.get('file_size')
            file_hash = response.get('file_hash')
            
            # Send ready confirmation
            ready_response = {'status': 'ready'}
            self.socket.send(json.dumps(ready_response).encode('utf-8'))
            
            # Determine target directory
            target_dir = download_dir if download_dir else self.download_dir
            
            # Prepare to receive file
            target_path = os.path.join(target_dir, filename)
            
            # Check if file exists and handle duplicates
            if os.path.exists(target_path):
                name, ext = os.path.splitext(filename)
                version = 1
                while os.path.exists(target_path):
                    new_filename = f"{name}_v{version}{ext}"
                    target_path = os.path.join(target_dir, new_filename)
                    version += 1
            
            # Receive file data
            received_size = 0
            hash_obj = hashlib.sha256()
            
            with open(target_path, 'wb') as f:
                while received_size < file_size:
                    chunk_size = min(4096, file_size - received_size)
                    chunk = self.socket.recv(chunk_size)
                    if not chunk:
                        break
                    
                    hash_obj.update(chunk)
                    f.write(chunk)
                    received_size += len(chunk)
                    
                    # Update progress
                    if progress_callback:
                        progress = (received_size / file_size) * 100
                        progress_callback(progress)
            
            # Verify file integrity
            calculated_hash = hash_obj.hexdigest()
            if calculated_hash == file_hash:
                logging.info(f"File {filename} downloaded successfully")
                return True, f"Downloaded to {target_path}"
            else:
                logging.error(f"File integrity check failed for {filename}")
                # Delete the corrupted file
                os.remove(target_path)
                return False, "File integrity check failed"
                
        except Exception as e:
            logging.error(f"Error in download_file: {e}")
            self.disconnect()
            return False, str(e)

class FileClientGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("File Sharing Client")
        self.root.geometry("800x600")
        self.root.minsize(800, 600)
        
        # Set background color
        self.root.configure(bg="#f0f0f0")
        
        # Initialize client
        self.client = None
        
        # Setup UI
        self.setup_ui()
        
        # Center window
        self.center_window()
    
    def center_window(self):
        """Center the window on the screen"""
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")
    
    def setup_ui(self):
        """Set up the main UI components"""
        # Main container with padding
        main_frame = ttk.Frame(self.root, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Top section - Connection
        self.create_connection_section(main_frame)
        
        # Middle section - File list
        self.create_file_list_section(main_frame)
        
        # Bottom section - Transfer status
        self.create_transfer_section(main_frame)
    
    def create_connection_section(self, parent):
        """Create the connection section"""
        conn_frame = ttk.LabelFrame(parent, text="Server Connection", padding=10)
        conn_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Grid layout for connection settings
        ttk.Label(conn_frame, text="Host:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.host_var = tk.StringVar(value="localhost")
        host_entry = ttk.Entry(conn_frame, textvariable=self.host_var, width=20)
        host_entry.grid(row=0, column=1, padx=5, pady=5, sticky=tk.W)
        
        ttk.Label(conn_frame, text="Port:").grid(row=0, column=2, padx=5, pady=5, sticky=tk.W)
        self.port_var = tk.StringVar(value="9999")
        port_entry = ttk.Entry(conn_frame, textvariable=self.port_var, width=10)
        port_entry.grid(row=0, column=3, padx=5, pady=5, sticky=tk.W)
        
        # Connection buttons
        self.connect_btn = ttk.Button(conn_frame, text="Connect", command=self.connect_to_server)
        self.connect_btn.grid(row=0, column=4, padx=5, pady=5)
        
        self.disconnect_btn = ttk.Button(conn_frame, text="Disconnect", command=self.disconnect_from_server, state=tk.DISABLED)
        self.disconnect_btn.grid(row=0, column=5, padx=5, pady=5)
        
        # Status indicator
        ttk.Label(conn_frame, text="Status:").grid(row=0, column=6, padx=(10, 5), pady=5, sticky=tk.W)
        self.status_var = tk.StringVar(value="Not connected")
        self.status_label = ttk.Label(conn_frame, textvariable=self.status_var)
        self.status_label.grid(row=0, column=7, padx=5, pady=5, sticky=tk.W)
    
    def create_file_list_section(self, parent):
        """Create the file list section"""
        file_frame = ttk.LabelFrame(parent, text="Server Files", padding=10)
        file_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Toolbar
        toolbar = ttk.Frame(file_frame)
        toolbar.pack(fill=tk.X, pady=(0, 5))
        
        self.refresh_btn = ttk.Button(toolbar, text="Refresh", command=self.refresh_file_list, state=tk.DISABLED)
        self.refresh_btn.pack(side=tk.LEFT, padx=5)
        
        self.upload_btn = ttk.Button(toolbar, text="Upload", command=self.upload_file, state=tk.DISABLED)
        self.upload_btn.pack(side=tk.LEFT, padx=5)
        
        self.download_btn = ttk.Button(toolbar, text="Download", command=self.download_selected, state=tk.DISABLED)
        self.download_btn.pack(side=tk.LEFT, padx=5)
        
        # File list with scrollbars
        list_frame = ttk.Frame(file_frame)
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        # Create Treeview
        self.file_tree = ttk.Treeview(list_frame, columns=("name", "size", "modified"), show="headings")
        
        # Define headings
        self.file_tree.heading("name", text="Filename")
        self.file_tree.heading("size", text="Size")
        self.file_tree.heading("modified", text="Modified Date")
        
        # Define columns
        self.file_tree.column("name", width=300, anchor=tk.W)
        self.file_tree.column("size", width=100, anchor=tk.E)
        self.file_tree.column("modified", width=150, anchor=tk.CENTER)
        
        # Add scrollbars
        y_scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.file_tree.yview)
        x_scrollbar = ttk.Scrollbar(list_frame, orient=tk.HORIZONTAL, command=self.file_tree.xview)
        self.file_tree.configure(yscrollcommand=y_scrollbar.set, xscrollcommand=x_scrollbar.set)
        
        # Pack everything
        self.file_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        y_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        x_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Bind double-click to download
        self.file_tree.bind("<Double-1>", lambda event: self.download_selected())
    
    def create_transfer_section(self, parent):
        """Create the transfer status section"""
        transfer_frame = ttk.LabelFrame(parent, text="Transfer Status", padding=10)
        transfer_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Transfer status label
        self.transfer_status_var = tk.StringVar(value="No transfer in progress")
        self.transfer_label = ttk.Label(transfer_frame, textvariable=self.transfer_status_var)
        self.transfer_label.pack(fill=tk.X, pady=(0, 5))
        
        # Progress bar
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(transfer_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill=tk.X)
    
    def connect_to_server(self):
        """Connect to the server"""
        host = self.host_var.get()
        try:
            port = int(self.port_var.get())
        except ValueError:
            messagebox.showerror("Error", "Port must be a number")
            return
        
        # Initialize client
        self.client = FileClient(host, port)
        
        # Disable buttons during connection
        self.set_buttons_state(False)
        self.status_var.set("Connecting...")
        
        # Connect in a separate thread
        def connect_thread():
            success = self.client.connect()
            
            # Update UI in the main thread
            self.root.after(0, lambda: self.connection_complete(success))
        
        threading.Thread(target=connect_thread, daemon=True).start()
    
    def disconnect_from_server(self):
        """Disconnect from the server"""
        if not self.client or not self.client.connected:
            return
        
        # Disable buttons during disconnection
        self.set_buttons_state(False)
        self.status_var.set("Disconnecting...")
        
        # Disconnect in a separate thread
        def disconnect_thread():
            self.client.disconnect()
            
            # Update UI in the main thread
            self.root.after(0, lambda: self.disconnection_complete())
        
        threading.Thread(target=disconnect_thread, daemon=True).start()
    
    def connection_complete(self, success):
        """Handle connection completion"""
        if success:
            self.status_var.set("Connected to server")
            self.set_connected_state(True)
            self.refresh_file_list()
        else:
            self.status_var.set("Connection failed")
            messagebox.showerror("Connection Error", "Failed to connect to server. Make sure the server is running.")
            self.set_connected_state(False)
    
    def disconnection_complete(self):
        """Handle disconnection completion"""
        self.status_var.set("Disconnected from server")
        self.set_connected_state(False)
        self.clear_file_list()
    
    def set_connected_state(self, connected):
        """Update UI based on connection state"""
        if connected:
            self.connect_btn.config(state=tk.DISABLED)
            self.disconnect_btn.config(state=tk.NORMAL)
            self.refresh_btn.config(state=tk.NORMAL)
            self.upload_btn.config(state=tk.NORMAL)
            self.download_btn.config(state=tk.NORMAL)
        else:
            self.connect_btn.config(state=tk.NORMAL)
            self.disconnect_btn.config(state=tk.DISABLED)
            self.refresh_btn.config(state=tk.DISABLED)
            self.upload_btn.config(state=tk.DISABLED)
            self.download_btn.config(state=tk.DISABLED)
    
    def set_buttons_state(self, enabled=True):
        """Enable or disable buttons during operations"""
        state = tk.NORMAL if enabled else tk.DISABLED
        self.connect_btn.config(state=state)
        self.disconnect_btn.config(state=state)
        self.refresh_btn.config(state=state)
        self.upload_btn.config(state=state)
        self.download_btn.config(state=state)
    
    def refresh_file_list(self):
        """Refresh the file list from the server"""
        if not self.client or not self.client.connected:
            return
        
        self.set_buttons_state(False)
        self.status_var.set("Refreshing file list...")
        
        def refresh_thread():
            files = self.client.list_files()
            
            # Update UI in the main thread
            self.root.after(0, lambda: self.update_file_list(files))
        
        threading.Thread(target=refresh_thread, daemon=True).start()
    
    def update_file_list(self, files):
        """Update the file list with data from server"""
        self.clear_file_list()
        
        if files is None:
            self.status_var.set("Failed to retrieve file list")
            messagebox.showerror("Error", "Failed to retrieve file list")
            self.set_buttons_state(True)
            return
        
        # Insert files into treeview
        for file_info in files:
            name = file_info.get('name', '')
            size = file_info.get('size', 0)
            modified = file_info.get('modified', '')
            
            # Format size
            size_str = self.format_size(size)
            
            self.file_tree.insert('', tk.END, iid=name, values=(name, size_str, modified))
        
        self.status_var.set(f"Found {len(files)} files on server")
        self.set_buttons_state(True)
    
    def clear_file_list(self):
        """Clear the file list"""
        for item in self.file_tree.get_children():
            self.file_tree.delete(item)
    
    def upload_file(self):
        """Upload a file to the server"""
        if not self.client or not self.client.connected:
            return
        
        # Ask user to select a file
        file_path = filedialog.askopenfilename(
            title="Select File to Upload",
            filetypes=[("All Files", "*.*")]
        )
        
        if not file_path:
            return
        
        filename = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        
        # Disable buttons during upload
        self.set_buttons_state(False)
        self.transfer_status_var.set(f"Uploading {filename}...")
        self.progress_var.set(0)
        
        # Upload in a separate thread
        def upload_thread():
            def update_progress(progress):
                self.progress_var.set(progress)
            
            success, message = self.client.upload_file(file_path, update_progress)
            
            # Update UI in the main thread
            self.root.after(0, lambda: self.upload_complete(success, message, filename))
        
        threading.Thread(target=upload_thread, daemon=True).start()
    
    def upload_complete(self, success, message, filename):
        """Handle upload completion"""
        if success:
            self.status_var.set(f"Uploaded {filename} successfully")
            self.transfer_status_var.set(f"Upload complete: {filename}")
            self.refresh_file_list()
        else:
            self.status_var.set(f"Upload failed: {message}")
            self.transfer_status_var.set(f"Upload failed: {filename}")
            messagebox.showerror("Upload Error", message)
        
        self.set_buttons_state(True)
    
    def download_selected(self):
        """Download the selected file"""
        if not self.client or not self.client.connected:
            return
        
        selected = self.file_tree.selection()
        if not selected:
            messagebox.showinfo("Information", "No file selected")
            return
        
        filename = selected[0]  # The item ID is the filename
        
        # Ask user for download location
        download_dir = filedialog.askdirectory(title="Select Download Location")
        if not download_dir:
            return
        
        # Disable buttons during download
        self.set_buttons_state(False)
        self.transfer_status_var.set(f"Downloading {filename}...")
        self.progress_var.set(0)
        
        # Download in a separate thread
        def download_thread():
            def update_progress(progress):
                self.progress_var.set(progress)
            
            success, message = self.client.download_file(filename, download_dir, update_progress)
            
            # Update UI in the main thread
            self.root.after(0, lambda: self.download_complete(success, message, filename))
        
        threading.Thread(target=download_thread, daemon=True).start()
    
    def download_complete(self, success, message, filename):
        """Handle download completion"""
        if success:
            self.status_var.set(f"Downloaded {filename} successfully")
            self.transfer_status_var.set(f"Download complete: {filename}")
            messagebox.showinfo("Download Complete", message)
        else:
            self.status_var.set(f"Download failed: {message}")
            self.transfer_status_var.set(f"Download failed: {filename}")
            messagebox.showerror("Download Error", message)
        
        self.set_buttons_state(True)
    
    def format_size(self, size_bytes):
        """Format file size to human-readable format"""
        if size_bytes == 0:
            return "0 B"
        
        size_names = ("B", "KB", "MB", "GB", "TB")
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024
            i += 1
        
        return f"{size_bytes:.2f} {size_names[i]}"

if __name__ == "__main__":
    root = tk.Tk()
    app = FileClientGUI(root)
    root.mainloop()
