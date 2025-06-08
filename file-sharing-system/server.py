import socket
import threading
import os
import json
import hashlib
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    filename='server_log.txt',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class FileServer:
    def __init__(self, host='localhost', port=9999):
        self.host = host
        self.port = port
        self.server_socket = None
        self.clients = []
        self.storage_dir = 'server_files'
        
        # Create storage directory if it doesn't exist
        if not os.path.exists(self.storage_dir):
            os.makedirs(self.storage_dir)
            
        print(f"Server initialized. Files will be stored in '{self.storage_dir}'")
        logging.info(f"Server initialized on {host}:{port}")
    
    def start(self):
        """Start the server and listen for connections"""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            print(f"Server started on {self.host}:{self.port}")
            logging.info(f"Server started on {self.host}:{self.port}")
            
            while True:
                client_socket, address = self.server_socket.accept()
                print(f"New connection from {address}")
                logging.info(f"New connection from {address}")
                
                # Create a new thread to handle the client
                client_thread = threading.Thread(
                    target=self.handle_client,
                    args=(client_socket, address)
                )
                client_thread.daemon = True
                client_thread.start()
                self.clients.append(client_thread)
                
        except KeyboardInterrupt:
            print("Server shutting down...")
            logging.info("Server shutting down")
        except Exception as e:
            print(f"Error: {e}")
            logging.error(f"Server error: {e}")
        finally:
            if self.server_socket:
                self.server_socket.close()
    
    def handle_client(self, client_socket, address):
        """Handle client requests"""
        try:
            while True:
                # Receive the command header
                header_data = client_socket.recv(1024)
                if not header_data:
                    break
                
                # Parse the header
                header = json.loads(header_data.decode('utf-8'))
                command = header.get('command')
                
                if command == 'LIST':
                    self.handle_list(client_socket)
                elif command == 'UPLOAD':
                    self.handle_upload(client_socket, header)
                elif command == 'DOWNLOAD':
                    self.handle_download(client_socket, header)
                else:
                    response = {'status': 'error', 'message': 'Invalid command'}
                    client_socket.send(json.dumps(response).encode('utf-8'))
        
        except Exception as e:
            print(f"Error handling client {address}: {e}")
            logging.error(f"Error handling client {address}: {e}")
        finally:
            client_socket.close()
            print(f"Connection from {address} closed")
            logging.info(f"Connection from {address} closed")
    
    def handle_list(self, client_socket):
        """Handle LIST command - send list of available files"""
        try:
            files = []
            for filename in os.listdir(self.storage_dir):
                file_path = os.path.join(self.storage_dir, filename)
                if os.path.isfile(file_path):
                    file_size = os.path.getsize(file_path)
                    modified_time = os.path.getmtime(file_path)
                    modified_time_str = datetime.fromtimestamp(modified_time).strftime('%Y-%m-%d %H:%M:%S')
                    
                    files.append({
                        'name': filename,
                        'size': file_size,
                        'modified': modified_time_str
                    })
            
            response = {
                'status': 'success',
                'files': files
            }
            
            client_socket.send(json.dumps(response).encode('utf-8'))
            logging.info("Sent file list to client")
            
        except Exception as e:
            response = {'status': 'error', 'message': str(e)}
            client_socket.send(json.dumps(response).encode('utf-8'))
            logging.error(f"Error in LIST command: {e}")
    
    def handle_upload(self, client_socket, header):
        """Handle UPLOAD command - receive file from client"""
        filename = header.get('filename')
        file_size = header.get('file_size')
        file_hash = header.get('file_hash')
        
        if not all([filename, file_size, file_hash]):
            response = {'status': 'error', 'message': 'Missing file information'}
            client_socket.send(json.dumps(response).encode('utf-8'))
            return
        
        # Check if file exists and handle duplicates
        target_path = os.path.join(self.storage_dir, filename)
        if os.path.exists(target_path):
            # Handle duplicate - rename with version number
            name, ext = os.path.splitext(filename)
            version = 1
            while os.path.exists(target_path):
                new_filename = f"{name}_v{version}{ext}"
                target_path = os.path.join(self.storage_dir, new_filename)
                version += 1
            filename = os.path.basename(target_path)
        
        # Send ready signal to client
        response = {'status': 'ready', 'filename': filename}
        client_socket.send(json.dumps(response).encode('utf-8'))
        
        # Receive file data
        try:
            received_size = 0
            hash_obj = hashlib.sha256()
            
            with open(target_path, 'wb') as f:
                while received_size < file_size:
                    chunk_size = min(4096, file_size - received_size)
                    chunk = client_socket.recv(chunk_size)
                    if not chunk:
                        break
                    
                    hash_obj.update(chunk)
                    f.write(chunk)
                    received_size += len(chunk)
            
            # Verify file integrity
            calculated_hash = hash_obj.hexdigest()
            if calculated_hash == file_hash:
                response = {'status': 'success', 'message': f'File {filename} uploaded successfully'}
                logging.info(f"File {filename} uploaded successfully")
            else:
                response = {'status': 'error', 'message': 'File integrity check failed'}
                logging.error(f"File integrity check failed for {filename}")
                # Delete the corrupted file
                os.remove(target_path)
            
            client_socket.send(json.dumps(response).encode('utf-8'))
            
        except Exception as e:
            response = {'status': 'error', 'message': str(e)}
            client_socket.send(json.dumps(response).encode('utf-8'))
            logging.error(f"Error in UPLOAD command: {e}")
            # Clean up partial file
            if os.path.exists(target_path):
                os.remove(target_path)
    
    def handle_download(self, client_socket, header):
        """Handle DOWNLOAD command - send file to client"""
        filename = header.get('filename')
        
        if not filename:
            response = {'status': 'error', 'message': 'Missing filename'}
            client_socket.send(json.dumps(response).encode('utf-8'))
            return
        
        file_path = os.path.join(self.storage_dir, filename)
        
        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            response = {'status': 'error', 'message': 'File not found'}
            client_socket.send(json.dumps(response).encode('utf-8'))
            return
        
        try:
            file_size = os.path.getsize(file_path)
            
            # Calculate file hash
            hash_obj = hashlib.sha256()
            with open(file_path, 'rb') as f:
                while chunk := f.read(4096):
                    hash_obj.update(chunk)
            file_hash = hash_obj.hexdigest()
            
            # Send file info to client
            response = {
                'status': 'ready',
                'filename': filename,
                'file_size': file_size,
                'file_hash': file_hash
            }
            client_socket.send(json.dumps(response).encode('utf-8'))
            
            # Wait for client to confirm ready to receive
            client_response = json.loads(client_socket.recv(1024).decode('utf-8'))
            if client_response.get('status') != 'ready':
                return
            
            # Send file data
            with open(file_path, 'rb') as f:
                while chunk := f.read(4096):
                    client_socket.send(chunk)
            
            logging.info(f"File {filename} downloaded by client")
            
        except Exception as e:
            response = {'status': 'error', 'message': str(e)}
            client_socket.send(json.dumps(response).encode('utf-8'))
            logging.error(f"Error in DOWNLOAD command: {e}")

if __name__ == "__main__":
    server = FileServer()
    print("File Server started. Press Ctrl+C to stop.")
    server.start()
