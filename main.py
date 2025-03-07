import os, json, time, re
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, HTTPServer, BaseHTTPRequestHandler
import logging
import traceback

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='attendance_system.log'
)
logger = logging.getLogger('AttendanceSystem')

# Ensure required directories exist
def ensure_directories():
    """Create necessary directory structure if it doesn't exist"""
    try:
        # Create base directories
        os.makedirs("backend_dyna_files", exist_ok=True)
        
        # Create week and day subdirectories
        for week in range(1, 11):  # Assuming 10 weeks per term
            week_dir = f"backend_dyna_files/week{week}"
            os.makedirs(week_dir, exist_ok=True)
            
            for day in range(1, 8):  # Days 1-7
                day_dir = f"{week_dir}/{day}"
                os.makedirs(day_dir, exist_ok=True)
                
        logger.info("Directory structure verified")
    except Exception as e:
        logger.error(f"Failed to create directories: {str(e)}")
        logger.error(traceback.format_exc())

def get_time_info():
    """Get current time information including term, week, day, and period"""
    try:
        now = datetime.now()
        year = now.year
        month = now.month
        day = now.day
        time_secs = (now.hour * 3600) + (now.minute * 60)
        weekday = now.weekday()
        
        # Load term dates
        with open("backend_static_files/termdates.js", "r") as file:
            term_dates_js = file.read()
            term_dates_match = re.search(r'\{.*\}', term_dates_js)
            if not term_dates_match:
                raise ValueError("Invalid termdates.js format")
            terms = json.loads(term_dates_match.group(0))["datesecs"]
        
        # Determine current term
        current_term = None
        for n in range(0, 3):
            if time_secs >= terms[n] and time_secs < terms[n+1]:
                current_term = n  # term 1 to 4 (0-indexed)
                break
        
        if current_term is None:
            logger.warning("Could not determine current term")
            current_term = 0
        
        # Calculate term week and day
        january_first = datetime(year, 1, 1).weekday()
        term_start_day = terms[current_term] // 86400
        current_day = int(time.time()) // 86400
        first_weekday_of_term = (term_start_day + january_first) % 7
        current_term_day = current_day - term_start_day + 1
        current_term_week = int((current_term_day - first_weekday_of_term + 6) / 7) + 1
        
        # Determine current period
        with open("backend_static_files/periodtimes.js", "r") as file:
            period_js = file.read()
            period_match = re.search(r'\{.*\}', period_js)
            if not period_match:
                raise ValueError("Invalid periodtimes.js format")
            periods = json.loads(period_match.group(0))["times"]
        
        current_period = None
        for x in range(0, len(periods) - 1):
            if time_secs >= periods[x] and time_secs < periods[x+1]:
                current_period = x + 1  # period 1 to N (1-indexed for user clarity)
                break
        
        if current_period is None:
            logger.warning("Could not determine current period")
            current_period = 1
        
        return {
            "term": current_term + 1,  # Convert to 1-indexed for readability
            "week": current_term_week,
            "weekday": weekday + 1,    # Convert to 1-indexed for file paths
            "period": current_period
        }
    except Exception as e:
        logger.error(f"Error in get_time_info: {str(e)}")
        logger.error(traceback.format_exc())
        # Return fallback values
        return {
            "term": 1,
            "week": 1,
            "weekday": 1,
            "period": 1
        }

def log_attendance(data, room=1, class_id=1):
    """Save attendance data to the appropriate file"""
    try:
        # Get current time information
        time_info = get_time_info()
        week = time_info["week"]
        weekday = time_info["weekday"]
        period = time_info["period"]
        
        # Ensure the directory exists
        directory = f"backend_dyna_files/week{week}/{weekday}"
        os.makedirs(directory, exist_ok=True)
        
        # Create the filename
        filename = f"{directory}/c{class_id}p{period}.js"
        
        # Add timestamp to the data
        data["timestamp"] = int(time.time())
        data["human_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Write the data
        with open(filename, "w") as file:
            file.write(f"const presence = {json.dumps(data, indent=2)}")
            
        # Create a backup copy
        backup_dir = "backend_dyna_files/backups"
        os.makedirs(backup_dir, exist_ok=True)
        backup_file = f"{backup_dir}/c{class_id}p{period}_w{week}d{weekday}_{int(time.time())}.js"
        
        with open(backup_file, "w") as file:
            file.write(f"const presence = {json.dumps(data, indent=2)}")
        
        logger.info(f"Attendance logged: class={class_id}, room={room}, period={period}, week={week}, day={weekday}")
        return True
    except Exception as e:
        logger.error(f"Failed to log attendance: {str(e)}")
        logger.error(traceback.format_exc())
        return False

class AttendanceServer(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        """Override to use our custom logger"""
        logger.info(f"{self.address_string()} - {format%args}")
    
    def send_error_response(self, message="An error occurred"):
        """Send a JSON error response"""
        self.send_response(500)
        self.send_header('Content-type', 'application/json')
        self.send_header('Cache-Control', 'no-cache, no-store')
        self.end_headers()
        response = {"status": "error", "message": message}
        self.wfile.write(json.dumps(response).encode('utf-8'))
    
    def handle_static_file(self, filename, content_type):
        """Handle serving a static file"""
        try:
            self.send_response(200)
            self.send_header('Content-type', content_type)
            self.send_header('Cache-Control', 'no-cache, no-store')
            self.end_headers()
            with open(filename, 'rb') as file:
                self.wfile.write(file.read())
        except Exception as e:
            logger.error(f"Error serving {filename}: {str(e)}")
            self.send_error_response(f"Error loading {filename}")
    
    def do_GET(self):
        try:
            # Static HTML pages
            if self.path == '/':
                self.send_response(302)  # Redirect
                self.send_header('Location', '/room1')
                self.end_headers()
                return
                
            elif self.path == '/room1':
                self.handle_static_file('frontend_files/room1.htm', 'text/html')
                
            elif self.path == '/view':
                self.handle_static_file('frontend_files/view.htm', 'text/html')
            
            # JavaScript files
            elif self.path == '/class1.js':
                self.handle_static_file('backend_static_files/class1.js', 'application/javascript')
                
            elif self.path == '/todayclass1':
                # Get current time information for retrieving the correct file
                time_info = get_time_info()
                week = time_info["week"]
                weekday = time_info["weekday"]
                period = time_info["period"]
                
                file_path = f"backend_dyna_files/week{week}/{weekday}/c1p{period}.js"
                
                # If today's file doesn't exist, use a default file
                if not os.path.exists(file_path):
                    file_path = "backend_dyna_files/c1p2.js"
                    
                self.handle_static_file(file_path, 'application/javascript')
                
            elif self.path == '/system-info':
                # Provide system information for debugging
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Cache-Control', 'no-cache, no-store')
                self.end_headers()
                
                time_info = get_time_info()
                info = {
                    "status": "running",
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "term": time_info["term"],
                    "week": time_info["week"],
                    "weekday": time_info["weekday"],
                    "period": time_info["period"]
                }
                
                self.wfile.write(json.dumps(info).encode('utf-8'))
                
            else:
                self.send_response(404)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(b'404 - Not Found')
                
        except Exception as e:
            logger.error(f"Error handling GET request: {str(e)}")
            logger.error(traceback.format_exc())
            self.send_error_response("Server error processing your request")
    
    def do_POST(self):
        try:
            if self.path == '/attendenceroom1':
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                data = json.loads(post_data.decode('utf-8'))
                
                # Validate data format
                if 'here' not in data or not isinstance(data['here'], list):
                    self.send_error_response("Invalid data format")
                    return
                
                # Log the attendance data
                success = log_attendance(data, room=1, class_id=1)
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Cache-Control', 'no-cache, no-store')
                self.end_headers()
                
                if success:
                    response = {'status': 'success', 'message': 'Attendance recorded successfully'}
                else:
                    response = {'status': 'error', 'message': 'Failed to record attendance'}
                    
                self.wfile.write(json.dumps(response).encode('utf-8'))
            else:
                self.send_response(404)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(b'404 - Not Found')
                
        except json.JSONDecodeError:
            logger.error("Invalid JSON received")
            self.send_error_response("Invalid JSON data")
        except Exception as e:
            logger.error(f"Error handling POST request: {str(e)}")
            logger.error(traceback.format_exc())
            self.send_error_response("Server error processing your request")

if __name__ == '__main__':
    try:
        # Ensure all required directories exist
        ensure_directories()
        
        # Start the server
        port = 8000
        server_address = ('', port)
        httpd = HTTPServer(server_address, AttendanceServer)
        
        print(f"Server started at http://localhost:{port}")
        logger.info(f"Server started on port {port}")
        
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("Server stopped.")
        logger.info("Server stopped by user")
    except Exception as e:
        print(f"Server error: {str(e)}")
        logger.critical(f"Fatal server error: {str(e)}")
        logger.critical(traceback.format_exc())