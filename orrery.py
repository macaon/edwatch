import tkinter as tk
from tkinter import ttk
import json
import os
import time
from datetime import datetime
from dataclasses import dataclass
from typing import Dict, Optional, List
import math
import threading
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

@dataclass
class CelestialBody:
    body_id: int
    name: str
    type: str  # 'Star' or 'Planet' or 'Moon'
    parent_id: Optional[int]
    semi_major_axis: float = 0
    eccentricity: float = 0
    orbital_inclination: float = 0
    orbital_period: float = 0
    ascending_node: float = 0
    mean_anomaly: float = 0
    radius: float = 0
    mass: float = 0
    distance_from_arrival: float = 0
    # Additional properties for display
    planet_class: str = ""
    surface_temp: float = 0
    surface_gravity: float = 0
    atmosphere_type: str = ""
    terraform_state: str = ""
    is_landable: bool = False

class SystemOrrery(tk.Tk):
    def __init__(self):
        super().__init__()
        
        self.title("Elite Dangerous System Orrery")
        self.geometry("1200x800")
        
        # Configure grid
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        
        # System data
        self.bodies: Dict[int, CelestialBody] = {}
        self.system_name = "Waiting for system..."
        self.system_address = 0
        self.stars: List[int] = []
        
        # Create main frame
        self.main_frame = ttk.Frame(self)
        self.main_frame.grid(row=0, column=1, sticky="nsew")
        self.main_frame.grid_rowconfigure(1, weight=1)
        self.main_frame.grid_columnconfigure(0, weight=1)
        
        # Create canvas
        self.canvas = tk.Canvas(self.main_frame, bg='black')
        self.canvas.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        
        # Create info panel using Treeview
        self.info_frame = ttk.Frame(self)
        self.info_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        
        self.system_label = ttk.Label(self.info_frame, text=self.system_name, font=('Arial', 14))
        self.system_label.pack(anchor=tk.W)
        
        self.tree = ttk.Treeview(self.info_frame, selectmode='browse')
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree["columns"] = ("type", "distance")
        self.tree.column("#0", width=200)
        self.tree.column("type", width=100)
        self.tree.column("distance", width=100)
        self.tree.heading("#0", text="Name")
        self.tree.heading("type", text="Type")
        self.tree.heading("distance", text="Distance (ls)")
        
        # Canvas interaction variables
        self.center_x = 0
        self.center_y = 0
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.is_dragging = False
        self.focused_body = None
        
        # Bind canvas events
        self.canvas.bind('<ButtonPress-1>', self.start_drag)
        self.canvas.bind('<B1-Motion>', self.drag)
        self.canvas.bind('<ButtonRelease-1>', self.end_drag)
        self.canvas.bind('<MouseWheel>', self.zoom_canvas)
        self.tree.bind('<<TreeviewSelect>>', self.on_body_select)
        
        # Scale and animation
        self.scale_factor = 1e-9
        self.zoom = 1.0
        self.animation_time = 0
        self.animate = True
        
        # Start monitoring thread
        self.running = True
        self.monitor_thread = threading.Thread(target=self.monitor_logs, daemon=True)
        self.monitor_thread.start()
        
        # Start animation
        self.update_animation()
        
    def start_drag(self, event):
        self.drag_start_x = event.x
        self.drag_start_y = event.y
        self.is_dragging = True
    
    def drag(self, event):
        if self.is_dragging:
            dx = event.x - self.drag_start_x
            dy = event.y - self.drag_start_y
            self.center_x += dx
            self.center_y += dy
            self.drag_start_x = event.x
            self.drag_start_y = event.y
            self.draw_system()
    
    def end_drag(self, event):
        self.is_dragging = False
    
    def on_body_select(self, event):
        selection = self.tree.selection()
        if selection:
            item = self.tree.item(selection[0])
            body_id = item.get('tags', [None])[0]
            if body_id and body_id in self.bodies:
                self.focused_body = self.bodies[body_id]
                self.center_on_body(self.focused_body)
    
    def center_on_body(self, body):
        x, y = self.get_body_position(body)
        canvas_center_x = self.canvas.winfo_width() / 2
        canvas_center_y = self.canvas.winfo_height() / 2
        self.center_x = canvas_center_x - x
        self.center_y = canvas_center_y - y
        self.draw_system()
    
    def get_body_position(self, body: CelestialBody):
        """Get the current position of a body"""
        if body.parent_id is None or body.parent_id == 0:
            return (self.canvas.winfo_width() / 2 + self.center_x, 
                   self.canvas.winfo_height() / 2 + self.center_y)
            
        parent = self.bodies.get(body.parent_id)
        if parent is None:
            return (self.canvas.winfo_width() / 2 + self.center_x, 
                   self.canvas.winfo_height() / 2 + self.center_y)
            
        parent_x, parent_y = self.get_body_position(parent)
        offset_x, offset_y = self.calculate_position(body, self.animation_time)
        return (parent_x + offset_x, parent_y + offset_y)
    
    def update_body_list(self):
        self.tree.delete(*self.tree.get_children())
        
        # Sort bodies by semi-major axis for each parent
        parent_groups = {}
        for body in self.bodies.values():
            parent_id = body.parent_id if body.parent_id is not None else -1
            if parent_id not in parent_groups:
                parent_groups[parent_id] = []
            parent_groups[parent_id].append(body)
        
        # Add primary stars first
        for body in sorted(parent_groups.get(-1, []), key=lambda x: x.body_id):
            self.add_body_to_tree("", body)
            
        # Add planets and moons in order of semi-major axis
        for parent_id, children in parent_groups.items():
            if parent_id != -1:  # Skip primary stars
                for body in sorted(children, key=lambda x: x.semi_major_axis):
                    parent = "" if body.parent_id is None else str(body.parent_id)
                    self.add_body_to_tree(parent, body)
    
    def add_body_to_tree(self, parent, body):
        body_info = (
            f"Class: {body.planet_class}\n"
            f"Temperature: {body.surface_temp:.1f}K\n"
            f"Gravity: {body.surface_gravity:.1f}g\n"
            f"Atmosphere: {body.atmosphere_type}\n"
            f"Terraform State: {body.terraform_state}\n"
            f"Landable: {'Yes' if body.is_landable else 'No'}"
        )
        
        self.tree.insert(parent, 'end', iid=str(body.body_id), text=body.name,
                        values=(body.type, f"{body.distance_from_arrival:.1f}"),
                        tags=(body.body_id,))
    
    def process_log_entry(self, data: dict):
        if data['event'] == 'Scan':
            body_id = data.get('BodyID', 0)
            
            try:
                is_star = 'StarType' in data
                body = CelestialBody(
                    body_id=body_id,
                    name=data['BodyName'],
                    type='Star' if is_star else 'Planet',
                    parent_id=get_parent_id(data.get('Parents', [])),
                    semi_major_axis=float(data.get('SemiMajorAxis', 0)),
                    eccentricity=float(data.get('Eccentricity', 0)),
                    orbital_inclination=float(data.get('OrbitalInclination', 0)) * math.pi / 180.0,
                    orbital_period=float(data.get('OrbitalPeriod', 0)),
                    ascending_node=float(data.get('AscendingNode', 0)) * math.pi / 180.0,
                    mean_anomaly=float(data.get('MeanAnomaly', 0)) * math.pi / 180.0,
                    radius=float(data.get('Radius', 0)),
                    mass=float(data.get('StellarMass' if is_star else 'MassEM', 0)),
                    distance_from_arrival=float(data.get('DistanceFromArrivalLS', 0)),
                    # Additional properties
                    planet_class=data.get('PlanetClass', ''),
                    surface_temp=float(data.get('SurfaceTemperature', 0)),
                    surface_gravity=float(data.get('SurfaceGravity', 0)),
                    atmosphere_type=data.get('AtmosphereType', ''),
                    terraform_state=data.get('TerraformState', ''),
                    is_landable=data.get('Landable', False)
                )
                
                self.bodies[body_id] = body
                if is_star:
                    self.stars.append(body_id)
                    
            except Exception as e:
                logging.error(f"Error processing body data: {e}")
                
        self.after(0, self.draw_system)
        self.after(0, self.update_body_list)
    def monitor_logs(self):
        directory = os.path.expandvars(r'C:\Users\%USERNAME%\Saved Games\Frontier Developments\Elite Dangerous')
        logging.info(f"Monitoring directory: {directory}")
        
        while self.running:
            newest_file = self.get_newest_file(directory)
            if newest_file:
                logging.info(f"Reading from file: {newest_file}")
                try:
                    with open(newest_file, 'r', encoding='utf-8') as file:
                        file.seek(0, os.SEEK_END)
                        while self.running:
                            line = file.readline()
                            if line:
                                try:
                                    data = json.loads(line.strip())
                                    self.process_log_entry(data)
                                except json.JSONDecodeError as e:
                                    logging.error(f"Failed to parse log line: {e}")
                                    logging.error(f"Problematic line: {line}")
                            time.sleep(0.1)
                except FileNotFoundError:
                    logging.error(f"File not found: {newest_file}")
            time.sleep(1)
    
    def get_newest_file(self, directory):
        try:
            files = [os.path.join(directory, f) for f in os.listdir(directory) 
                    if f.startswith('Journal.') and f.endswith('.log')]
            files = [f for f in files if os.path.isfile(f)]
            if not files:
                return None
            return max(files, key=os.path.getmtime)
        except Exception as e:
            logging.error(f"Failed to get newest file: {e}")
            return None
    
    def on_closing(self):
        logging.info("Shutting down System Orrery")
        self.running = False
        self.destroy()

if __name__ == "__main__":
    logging.info("Starting Elite Dangerous System Orrery")
    app = SystemOrrery()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()

