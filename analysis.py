import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import json
import os
from collections import Counter
import datetime

# =========================
# Command Database Manager
# =========================

class CommandDatabaseManager:
    def __init__(self, root):
        self.root = root
        self.root.title("ActiMates Command Database Manager")
        self.root.geometry("1200x700")
        
        self.db_path = None
        self.commands = {}
        self.original_commands = {}
        self.modified = False
        
        self.build_ui()
        
        # Try to load default commands.json
        if os.path.exists("commands.json"):
            self.load_database("commands.json")
    
    def build_ui(self):
        # Menu bar
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Open Database...", command=self.open_database)
        file_menu.add_command(label="Save", command=self.save_database, accelerator="Ctrl+S")
        file_menu.add_command(label="Save As...", command=self.save_as_database)
        file_menu.add_separator()
        file_menu.add_command(label="Export CSV...", command=self.export_csv)
        file_menu.add_command(label="Import CSV...", command=self.import_csv)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.exit_app)
        
        edit_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Edit", menu=edit_menu)
        edit_menu.add_command(label="Rename Selected", command=self.rename_selected, accelerator="F2")
        edit_menu.add_command(label="Rename Multiple...", command=self.batch_rename)
        edit_menu.add_command(label="Reset to Unknown", command=self.reset_selected)
        edit_menu.add_separator()
        edit_menu.add_command(label="Find & Replace...", command=self.find_replace)
        
        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="View", menu=view_menu)
        view_menu.add_command(label="Show Statistics", command=self.show_statistics)
        view_menu.add_command(label="Show Only Named", command=lambda: self.filter_commands("named"))
        view_menu.add_command(label="Show Only Unknown", command=lambda: self.filter_commands("unknown"))
        view_menu.add_command(label="Show All", command=lambda: self.filter_commands("all"))
        
        # Bind keyboard shortcuts
        self.root.bind("<Control-s>", lambda e: self.save_database())
        self.root.bind("<F2>", lambda e: self.rename_selected())
        self.root.bind("<Control-f>", lambda e: self.find_replace())
        
        # Top toolbar
        toolbar = tk.Frame(self.root, relief=tk.RAISED, borderwidth=1)
        toolbar.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        
        tk.Button(toolbar, text="Open DB", command=self.open_database).pack(side=tk.LEFT, padx=2)
        tk.Button(toolbar, text="Save", command=self.save_database).pack(side=tk.LEFT, padx=2)
        tk.Button(toolbar, text="Rename", command=self.rename_selected).pack(side=tk.LEFT, padx=2)
        tk.Button(toolbar, text="Batch Rename", command=self.batch_rename).pack(side=tk.LEFT, padx=2)
        
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, padx=5, fill=tk.Y)
        
        tk.Label(toolbar, text="Search:").pack(side=tk.LEFT, padx=5)
        self.search_var = tk.StringVar()
        self.search_var.trace("w", self.on_search_changed)
        search_entry = tk.Entry(toolbar, textvariable=self.search_var, width=30)
        search_entry.pack(side=tk.LEFT, padx=2)
        
        tk.Button(toolbar, text="Clear", command=self.clear_search).pack(side=tk.LEFT, padx=2)
        
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, padx=5, fill=tk.Y)
        
        tk.Button(toolbar, text="Statistics", command=self.show_statistics).pack(side=tk.LEFT, padx=2)
        
        # Status bar (at top for info display)
        self.status_bar = tk.Label(self.root, text="No database loaded", 
                                   bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.TOP, fill=tk.X)
        
        # Main content area
        main_frame = tk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Command list (left side - 70%)
        list_frame = tk.Frame(main_frame)
        list_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        tk.Label(list_frame, text="Commands Database", font=("Arial", 10, "bold")).pack(anchor=tk.W)
        
        # Treeview with scrollbars
        tree_scroll_frame = tk.Frame(list_frame)
        tree_scroll_frame.pack(fill=tk.BOTH, expand=True)
        
        tree_yscroll = ttk.Scrollbar(tree_scroll_frame, orient=tk.VERTICAL)
        tree_xscroll = ttk.Scrollbar(tree_scroll_frame, orient=tk.HORIZONTAL)
        
        self.tree = ttk.Treeview(tree_scroll_frame, 
                                 columns=("Hash", "Name", "Status", "Occurrences"),
                                 show="headings",
                                 yscrollcommand=tree_yscroll.set,
                                 xscrollcommand=tree_xscroll.set)
        
        tree_yscroll.config(command=self.tree.yview)
        tree_xscroll.config(command=self.tree.xview)
        
        tree_yscroll.pack(side=tk.RIGHT, fill=tk.Y)
        tree_xscroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Configure columns
        self.tree.heading("Hash", text="Hash (SHA1)")
        self.tree.heading("Name", text="Command Name")
        self.tree.heading("Status", text="Status")
        self.tree.heading("Occurrences", text="Occurrences")
        
        self.tree.column("Hash", width=300)
        self.tree.column("Name", width=220)
        self.tree.column("Status", width=80)
        self.tree.column("Occurrences", width=100)
        
        # Bind double-click to rename
        self.tree.bind("<Double-1>", lambda e: self.rename_selected())
        
        # Details panel (right side - 30%)
        details_frame = tk.LabelFrame(main_frame, text="Details", padx=10, pady=10)
        details_frame.pack(side=tk.RIGHT, fill=tk.BOTH, padx=(10, 0))
        
        # Selected command info
        tk.Label(details_frame, text="Hash:", font=("Arial", 9, "bold")).grid(row=0, column=0, sticky=tk.W, pady=2)
        self.detail_hash = tk.Label(details_frame, text="-", wraplength=250, justify=tk.LEFT)
        self.detail_hash.grid(row=0, column=1, sticky=tk.W, pady=2)
        
        tk.Label(details_frame, text="Name:", font=("Arial", 9, "bold")).grid(row=1, column=0, sticky=tk.W, pady=2)
        self.detail_name = tk.Label(details_frame, text="-", wraplength=250, justify=tk.LEFT, fg="blue")
        self.detail_name.grid(row=1, column=1, sticky=tk.W, pady=2)
        
        tk.Label(details_frame, text="Status:", font=("Arial", 9, "bold")).grid(row=2, column=0, sticky=tk.W, pady=2)
        self.detail_status = tk.Label(details_frame, text="-")
        self.detail_status.grid(row=2, column=1, sticky=tk.W, pady=2)
        
        tk.Label(details_frame, text="Occurrences:", font=("Arial", 9, "bold")).grid(row=3, column=0, sticky=tk.W, pady=2)
        self.detail_occurrences = tk.Label(details_frame, text="-")
        self.detail_occurrences.grid(row=3, column=1, sticky=tk.W, pady=2)
        
        # Timestamps list
        tk.Label(details_frame, text="Timestamps:", font=("Arial", 9, "bold")).grid(row=4, column=0, sticky=tk.NW, pady=2)
        
        timestamp_frame = tk.Frame(details_frame)
        timestamp_frame.grid(row=4, column=1, sticky=tk.W, pady=2)
        
        timestamp_scroll = tk.Scrollbar(timestamp_frame, orient=tk.VERTICAL)
        self.timestamp_list = tk.Listbox(timestamp_frame, height=5, width=25, 
                                         yscrollcommand=timestamp_scroll.set)
        timestamp_scroll.config(command=self.timestamp_list.yview)
        
        self.timestamp_list.pack(side=tk.LEFT, fill=tk.BOTH)
        timestamp_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        ttk.Separator(details_frame, orient=tk.HORIZONTAL).grid(row=5, column=0, columnspan=2, sticky="ew", pady=10)
        
        # Quick actions
        tk.Label(details_frame, text="Quick Actions:", font=("Arial", 9, "bold")).grid(row=6, column=0, columnspan=2, sticky=tk.W, pady=5)
        
        tk.Button(details_frame, text="Rename", command=self.rename_selected, width=20).grid(row=7, column=0, columnspan=2, pady=2)
        tk.Button(details_frame, text="Copy Hash", command=self.copy_hash, width=20).grid(row=8, column=0, columnspan=2, pady=2)
        tk.Button(details_frame, text="Copy Name", command=self.copy_name, width=20).grid(row=9, column=0, columnspan=2, pady=2)
        tk.Button(details_frame, text="View All Timestamps", command=self.view_all_timestamps, width=20).grid(row=10, column=0, columnspan=2, pady=2)
        
        ttk.Separator(details_frame, orient=tk.HORIZONTAL).grid(row=11, column=0, columnspan=2, sticky="ew", pady=10)
        
        # Database stats
        tk.Label(details_frame, text="Database Stats:", font=("Arial", 9, "bold")).grid(row=12, column=0, columnspan=2, sticky=tk.W, pady=5)
        
        self.stats_total = tk.Label(details_frame, text="Total: 0")
        self.stats_total.grid(row=13, column=0, columnspan=2, sticky=tk.W, pady=2)
        
        self.stats_named = tk.Label(details_frame, text="Named: 0")
        self.stats_named.grid(row=14, column=0, columnspan=2, sticky=tk.W, pady=2)
        
        self.stats_unknown = tk.Label(details_frame, text="Unknown: 0")
        self.stats_unknown.grid(row=15, column=0, columnspan=2, sticky=tk.W, pady=2)
        
        # Bind selection event
        self.tree.bind("<<TreeviewSelect>>", self.on_selection_changed)
    
    def load_database(self, path):
        try:
            with open(path, "r") as f:
                data = json.load(f)
            
            # Support both old format (string) and new format (dict with name/timestamps)
            self.commands = {}
            for h, value in data.items():
                if isinstance(value, dict):
                    self.commands[h] = value
                else:
                    # Convert old format
                    self.commands[h] = {"name": value, "timestamps": []}
            
            self.original_commands = {k: v.copy() if isinstance(v, dict) else v 
                                     for k, v in self.commands.items()}
            self.db_path = path
            self.modified = False
            
            self.populate_tree()
            self.update_status(f"Loaded {len(self.commands)} commands from {os.path.basename(path)}")
            self.update_stats()
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load database:\n{e}")
    
    def populate_tree(self, filter_func=None):
        # Clear existing items
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # Add commands
        for hash_val, entry in sorted(self.commands.items(), key=lambda x: self._get_name(x[1])):
            name = self._get_name(entry)
            timestamps = self._get_timestamps(entry)
            status = "Unknown" if name.startswith("UNKNOWN_") else "Named"
            occurrences = len(timestamps)
            
            if filter_func is None or filter_func(name):
                self.tree.insert("", tk.END, values=(hash_val, name, status, occurrences),
                               tags=(status.lower(),))
        
        # Configure tag colors
        self.tree.tag_configure("named", foreground="green")
        self.tree.tag_configure("unknown", foreground="gray")
    
    def _get_name(self, entry):
        """Helper to get name from entry (supports old and new format)"""
        if isinstance(entry, dict):
            return entry.get("name", "UNKNOWN")
        return entry
    
    def _get_timestamps(self, entry):
        """Helper to get timestamps from entry"""
        if isinstance(entry, dict):
            return entry.get("timestamps", [])
        return []
    
    def update_status(self, message):
        self.status_bar.config(text=message)
        if self.modified:
            self.root.title("ActiMates Command Database Manager - *Modified*")
        else:
            self.root.title("ActiMates Command Database Manager")
    
    def update_stats(self):
        total = len(self.commands)
        unknown = sum(1 for entry in self.commands.values() 
                     if self._get_name(entry).startswith("UNKNOWN_"))
        named = total - unknown
        
        self.stats_total.config(text=f"Total: {total}")
        self.stats_named.config(text=f"Named: {named} ({named/total*100:.1f}%)" if total > 0 else "Named: 0")
        self.stats_unknown.config(text=f"Unknown: {unknown} ({unknown/total*100:.1f}%)" if total > 0 else "Unknown: 0")
    
    def on_selection_changed(self, event):
        selection = self.tree.selection()
        if selection:
            item = self.tree.item(selection[0])
            values = item['values']
            
            hash_val = values[0]
            name = values[1]
            status = values[2]
            occurrences = values[3]
            
            # Get full entry for timestamps
            entry = self.commands.get(hash_val)
            timestamps = self._get_timestamps(entry)
            
            self.detail_hash.config(text=hash_val[:16] + "...")
            self.detail_name.config(text=name)
            self.detail_status.config(text=status)
            self.detail_occurrences.config(text=str(occurrences))
            
            # Update timestamp list (show first 5)
            self.timestamp_list.delete(0, tk.END)
            for i, ts in enumerate(timestamps[:5]):
                time_str = self._format_timestamp(ts)
                self.timestamp_list.insert(tk.END, time_str)
            
            if len(timestamps) > 5:
                self.timestamp_list.insert(tk.END, f"... +{len(timestamps)-5} more")
    
    def _format_timestamp(self, seconds):
        """Format timestamp as HH:MM:SS.mmm"""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = seconds % 60
        return f"{h:02}:{m:02}:{s:06.3f}"
    
    def on_search_changed(self, *args):
        search_text = self.search_var.get().lower()
        if not search_text:
            self.populate_tree()
        else:
            def filter_func(name):
                return search_text in name.lower()
            self.populate_tree(filter_func)
    
    def clear_search(self):
        self.search_var.set("")
    
    def open_database(self):
        if self.modified:
            response = messagebox.askyesnocancel("Unsaved Changes", 
                                                 "You have unsaved changes. Save before opening?")
            if response is True:
                self.save_database()
            elif response is None:
                return
        
        path = filedialog.askopenfilename(
            title="Open Command Database",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        
        if path:
            self.load_database(path)
    
    def save_database(self):
        if not self.db_path:
            self.save_as_database()
            return
        
        try:
            with open(self.db_path, "w") as f:
                json.dump(self.commands, f, indent=2)
            
            self.original_commands = self.commands.copy()
            self.modified = False
            self.update_status(f"Saved to {os.path.basename(self.db_path)}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save database:\n{e}")
    
    def save_as_database(self):
        path = filedialog.asksaveasfilename(
            title="Save Command Database",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        
        if path:
            self.db_path = path
            self.save_database()
    
    def rename_selected(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a command to rename.")
            return
        
        item = self.tree.item(selection[0])
        hash_val = item['values'][0]
        entry = self.commands.get(hash_val)
        old_name = self._get_name(entry)
        
        new_name = simpledialog.askstring("Rename Command", 
                                          f"Enter new name for:\n{hash_val[:16]}...",
                                          initialvalue=old_name)
        
        if new_name and new_name != old_name:
            # Preserve timestamps
            if isinstance(entry, dict):
                self.commands[hash_val]["name"] = new_name
            else:
                self.commands[hash_val] = {"name": new_name, "timestamps": []}
            
            self.modified = True
            self.populate_tree()
            self.update_status(f"Renamed to '{new_name}'")
            self.update_stats()
    
    def batch_rename(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Batch Rename")
        dialog.geometry("500x300")
        dialog.transient(self.root)
        dialog.grab_set()
        
        tk.Label(dialog, text="Batch Rename Commands", font=("Arial", 12, "bold")).pack(pady=10)
        
        frame = tk.Frame(dialog)
        frame.pack(padx=20, pady=10, fill=tk.BOTH, expand=True)
        
        tk.Label(frame, text="Prefix to add:").grid(row=0, column=0, sticky=tk.W, pady=5)
        prefix_var = tk.StringVar()
        tk.Entry(frame, textvariable=prefix_var, width=30).grid(row=0, column=1, pady=5)
        
        tk.Label(frame, text="Suffix to add:").grid(row=1, column=0, sticky=tk.W, pady=5)
        suffix_var = tk.StringVar()
        tk.Entry(frame, textvariable=suffix_var, width=30).grid(row=1, column=1, pady=5)
        
        tk.Label(frame, text="Find text:").grid(row=2, column=0, sticky=tk.W, pady=5)
        find_var = tk.StringVar()
        tk.Entry(frame, textvariable=find_var, width=30).grid(row=2, column=1, pady=5)
        
        tk.Label(frame, text="Replace with:").grid(row=3, column=0, sticky=tk.W, pady=5)
        replace_var = tk.StringVar()
        tk.Entry(frame, textvariable=replace_var, width=30).grid(row=3, column=1, pady=5)
        
        apply_to_var = tk.StringVar(value="all")
        tk.Label(frame, text="Apply to:").grid(row=4, column=0, sticky=tk.W, pady=5)
        apply_frame = tk.Frame(frame)
        apply_frame.grid(row=4, column=1, sticky=tk.W)
        tk.Radiobutton(apply_frame, text="All", variable=apply_to_var, value="all").pack(side=tk.LEFT)
        tk.Radiobutton(apply_frame, text="Unknown only", variable=apply_to_var, value="unknown").pack(side=tk.LEFT)
        tk.Radiobutton(apply_frame, text="Named only", variable=apply_to_var, value="named").pack(side=tk.LEFT)
        
        def apply_batch():
            prefix = prefix_var.get()
            suffix = suffix_var.get()
            find = find_var.get()
            replace = replace_var.get()
            apply_to = apply_to_var.get()
            
            count = 0
            for hash_val, entry in list(self.commands.items()):
                name = self._get_name(entry)
                should_apply = False
                
                if apply_to == "all":
                    should_apply = True
                elif apply_to == "unknown" and name.startswith("UNKNOWN_"):
                    should_apply = True
                elif apply_to == "named" and not name.startswith("UNKNOWN_"):
                    should_apply = True
                
                if should_apply:
                    new_name = name
                    if find and replace is not None:
                        new_name = new_name.replace(find, replace)
                    new_name = prefix + new_name + suffix
                    
                    if new_name != name:
                        if isinstance(entry, dict):
                            self.commands[hash_val]["name"] = new_name
                        else:
                            self.commands[hash_val] = {"name": new_name, "timestamps": []}
                        count += 1
            
            if count > 0:
                self.modified = True
                self.populate_tree()
                self.update_status(f"Batch renamed {count} commands")
                self.update_stats()
            
            dialog.destroy()
        
        button_frame = tk.Frame(dialog)
        button_frame.pack(pady=10)
        tk.Button(button_frame, text="Apply", command=apply_batch, width=15).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Cancel", command=dialog.destroy, width=15).pack(side=tk.LEFT, padx=5)
    
    def reset_selected(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select commands to reset.")
            return
        
        if not messagebox.askyesno("Confirm Reset", 
                                   f"Reset {len(selection)} selected command(s) to UNKNOWN?"):
            return
        
        for item_id in selection:
            item = self.tree.item(item_id)
            hash_val = item['values'][0]
            entry = self.commands[hash_val]
            
            if isinstance(entry, dict):
                entry["name"] = f"UNKNOWN_{hash_val[:8]}"
            else:
                self.commands[hash_val] = {"name": f"UNKNOWN_{hash_val[:8]}", "timestamps": []}
        
        self.modified = True
        self.populate_tree()
        self.update_status(f"Reset {len(selection)} commands")
        self.update_stats()
    
    def find_replace(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Find & Replace")
        dialog.geometry("400x200")
        dialog.transient(self.root)
        dialog.grab_set()
        
        tk.Label(dialog, text="Find & Replace", font=("Arial", 12, "bold")).pack(pady=10)
        
        frame = tk.Frame(dialog)
        frame.pack(padx=20, pady=10)
        
        tk.Label(frame, text="Find:").grid(row=0, column=0, sticky=tk.W, pady=5)
        find_var = tk.StringVar()
        tk.Entry(frame, textvariable=find_var, width=30).grid(row=0, column=1, pady=5)
        
        tk.Label(frame, text="Replace with:").grid(row=1, column=0, sticky=tk.W, pady=5)
        replace_var = tk.StringVar()
        tk.Entry(frame, textvariable=replace_var, width=30).grid(row=1, column=1, pady=5)
        
        def do_replace():
            find = find_var.get()
            replace = replace_var.get()
            
            if not find:
                messagebox.showwarning("Empty Find", "Please enter text to find.")
                return
            
            count = 0
            for hash_val, entry in list(self.commands.items()):
                name = self._get_name(entry)
                if find in name:
                    new_name = name.replace(find, replace)
                    if isinstance(entry, dict):
                        self.commands[hash_val]["name"] = new_name
                    else:
                        self.commands[hash_val] = {"name": new_name, "timestamps": []}
                    count += 1
            
            if count > 0:
                self.modified = True
                self.populate_tree()
                self.update_status(f"Replaced in {count} commands")
                self.update_stats()
                dialog.destroy()
            else:
                messagebox.showinfo("No Matches", f"No commands found containing '{find}'")
        
        button_frame = tk.Frame(dialog)
        button_frame.pack(pady=10)
        tk.Button(button_frame, text="Replace All", command=do_replace, width=15).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Cancel", command=dialog.destroy, width=15).pack(side=tk.LEFT, padx=5)
    
    def filter_commands(self, filter_type):
        if filter_type == "named":
            self.populate_tree(lambda name: not name.startswith("UNKNOWN_"))
            self.update_status("Showing only named commands")
        elif filter_type == "unknown":
            self.populate_tree(lambda name: name.startswith("UNKNOWN_"))
            self.update_status("Showing only unknown commands")
        else:
            self.populate_tree()
            self.update_status("Showing all commands")
    
    def show_statistics(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Database Statistics")
        dialog.geometry("500x400")
        dialog.transient(self.root)
        
        tk.Label(dialog, text="Database Statistics", font=("Arial", 14, "bold")).pack(pady=10)
        
        text = tk.Text(dialog, wrap=tk.WORD, padx=10, pady=10)
        text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Calculate stats
        total = len(self.commands)
        unknown = sum(1 for entry in self.commands.values() 
                     if self._get_name(entry).startswith("UNKNOWN_"))
        named = total - unknown
        
        # Calculate total occurrences
        total_occurrences = sum(len(self._get_timestamps(entry)) 
                               for entry in self.commands.values())
        
        # Get most common prefixes
        prefixes = []
        for entry in self.commands.values():
            name = self._get_name(entry)
            if not name.startswith("UNKNOWN_"):
                parts = name.split("_")
                if parts:
                    prefixes.append(parts[0])
        
        prefix_counts = Counter(prefixes).most_common(10)
        
        # Build stats text
        stats_text = f"""
DATABASE OVERVIEW
{'='*50}
File: {os.path.basename(self.db_path) if self.db_path else 'Not saved'}
Total Commands: {total:,}
Named Commands: {named:,} ({named/total*100:.1f}%)
Unknown Commands: {unknown:,} ({unknown/total*100:.1f}%)
Total Occurrences: {total_occurrences:,}

TOP 10 COMMAND PREFIXES
{'='*50}
"""
        
        if prefix_counts:
            for prefix, count in prefix_counts:
                stats_text += f"{prefix}: {count:,} commands\n"
        else:
            stats_text += "No named commands yet\n"
        
        stats_text += f"\n{'='*50}\n"
        stats_text += f"Last modified: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        
        text.insert("1.0", stats_text)
        text.config(state=tk.DISABLED)
        
        tk.Button(dialog, text="Close", command=dialog.destroy, width=15).pack(pady=10)
    
    def copy_hash(self):
        selection = self.tree.selection()
        if selection:
            item = self.tree.item(selection[0])
            hash_val = item['values'][0]
            self.root.clipboard_clear()
            self.root.clipboard_append(hash_val)
            self.update_status("Hash copied to clipboard")
    
    def copy_name(self):
        selection = self.tree.selection()
        if selection:
            item = self.tree.item(selection[0])
            name = item['values'][1]
            self.root.clipboard_clear()
            self.root.clipboard_append(name)
            self.update_status("Name copied to clipboard")
    
    def view_all_timestamps(self):
        """Show all timestamps for selected command in a dialog"""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a command first.")
            return
        
        item = self.tree.item(selection[0])
        hash_val = item['values'][0]
        name = item['values'][1]
        
        entry = self.commands.get(hash_val)
        timestamps = self._get_timestamps(entry)
        
        if not timestamps:
            messagebox.showinfo("No Timestamps", "This command has no recorded timestamps.")
            return
        
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Timestamps for {name}")
        dialog.geometry("400x500")
        dialog.transient(self.root)
        
        tk.Label(dialog, text=f"All Timestamps for:", font=("Arial", 10, "bold")).pack(pady=5)
        tk.Label(dialog, text=name, font=("Arial", 10), fg="blue").pack(pady=5)
        tk.Label(dialog, text=f"Total occurrences: {len(timestamps)}", font=("Arial", 9)).pack(pady=5)
        
        # Listbox with all timestamps
        frame = tk.Frame(dialog)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        scrollbar = tk.Scrollbar(frame, orient=tk.VERTICAL)
        listbox = tk.Listbox(frame, yscrollcommand=scrollbar.set)
        scrollbar.config(command=listbox.yview)
        
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        for i, ts in enumerate(timestamps, 1):
            time_str = self._format_timestamp(ts)
            listbox.insert(tk.END, f"{i}. {time_str}")
        
        tk.Button(dialog, text="Close", command=dialog.destroy, width=15).pack(pady=10)
    
    def export_csv(self):
        if not self.commands:
            messagebox.showwarning("No Data", "No database loaded.")
            return
        
        path = filedialog.asksaveasfilename(
            title="Export to CSV",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        
        if path:
            try:
                import csv
                with open(path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(["Hash", "Name", "Status", "Occurrences", "Timestamps"])
                    
                    for hash_val, entry in sorted(self.commands.items(), key=lambda x: self._get_name(x[1])):
                        name = self._get_name(entry)
                        timestamps = self._get_timestamps(entry)
                        status = "Unknown" if name.startswith("UNKNOWN_") else "Named"
                        occurrences = len(timestamps)
                        timestamps_str = ";".join([str(ts) for ts in timestamps])
                        
                        writer.writerow([hash_val, name, status, occurrences, timestamps_str])
                
                self.update_status(f"Exported to {os.path.basename(path)}")
                messagebox.showinfo("Success", f"Exported {len(self.commands)} commands to CSV")
            
            except Exception as e:
                messagebox.showerror("Error", f"Failed to export:\n{e}")
    
    def import_csv(self):
        path = filedialog.askopenfilename(
            title="Import from CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        
        if path:
            try:
                import csv
                imported = {}
                with open(path, "r", encoding="utf-8") as f:
                    reader = csv.reader(f)
                    header = next(reader)  # Read header
                    
                    for row in reader:
                        if len(row) >= 2:
                            hash_val = row[0]
                            name = row[1]
                            timestamps = []
                            
                            # Check if timestamps column exists
                            if len(row) >= 5 and row[4]:
                                try:
                                    timestamps = [float(ts) for ts in row[4].split(";") if ts]
                                except:
                                    pass
                            
                            imported[hash_val] = {"name": name, "timestamps": timestamps}
                
                if messagebox.askyesno("Confirm Import", 
                                      f"Import {len(imported)} commands? This will merge with existing data."):
                    # Merge timestamps
                    for hash_val, entry in imported.items():
                        if hash_val in self.commands:
                            existing = self.commands[hash_val]
                            existing_ts = self._get_timestamps(existing)
                            new_ts = entry["timestamps"]
                            merged_ts = sorted(list(set(existing_ts + new_ts)))
                            self.commands[hash_val] = {"name": entry["name"], "timestamps": merged_ts}
                        else:
                            self.commands[hash_val] = entry
                    
                    self.modified = True
                    self.populate_tree()
                    self.update_status(f"Imported {len(imported)} commands")
                    self.update_stats()
            
            except Exception as e:
                messagebox.showerror("Error", f"Failed to import:\n{e}")
    
    def exit_app(self):
        if self.modified:
            response = messagebox.askyesnocancel("Unsaved Changes", 
                                                 "You have unsaved changes. Save before exiting?")
            if response is True:
                self.save_database()
            elif response is None:
                return
        
        self.root.destroy()


# =========================
# Main
# =========================

if __name__ == "__main__":
    root = tk.Tk()
    app = CommandDatabaseManager(root)
    root.mainloop()