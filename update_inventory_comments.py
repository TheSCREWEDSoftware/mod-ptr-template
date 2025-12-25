#!/usr/bin/env python3
"""
Script to update comments in mod_ptrtemplate_inventory SQL files.
Updates comments with race, class, quantity, slot, and item names from database.
"""

import os
import re
import shutil
import csv
import mysql.connector
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'acore',
    'password': 'acore',
    'database': 'acore_world'
}



# Slot mappings
SLOTS = {
    0: 'Head',
    1: 'Neck',
    2: 'Shoulders',
    3: 'Body',
    4: 'Chest',
    5: 'Waist',
    6: 'Legs',
    7: 'Feet',
    8: 'Wrists',
    9: 'Hands',
    10: 'Finger 1',
    11: 'Finger 2',
    12: 'Trinket 1',
    13: 'Trinket 2',
    14: 'Back',
    15: 'Main Hand',
    16: 'Off Hand',
    17: 'Ranged',
    18: 'Tabard',
    19: 'Equipped Bag 1',
    20: 'Equipped Bag 2',
    21: 'Equipped Bag 3',
    22: 'Equipped Bag 4',
    # Slots 23-38: Main Backpack
    **{i: f'Backpack Slot {i-22}' for i in range(23, 39)},
    # Slots 39-66: Main Bank
    **{i: f'Bank Slot {i-38}' for i in range(39, 67)},
    # Slots 67-73: Bank Bags
    **{i: f'Bank Bag {i-66}' for i in range(67, 74)},
    # Slots 86-117: Keys in Keyring
    **{i: f'Keyring Slot {i-85}' for i in range(86, 118)},
    # Slots 118-135: Currencies
    **{i: f'Currency Slot {i-117}' for i in range(118, 136)},
    # Other slots
    43: 'Money',
    150: 'Ammo'
}

class InventoryCommentUpdater:
    def __init__(self):
        self.db_connection = None
        self.item_cache = {}
        self.duplicate_items = set()
        self.enchant_cache = {}
        
    def connect_to_database(self):
        """Connect to the MySQL database."""
        try:
            self.db_connection = mysql.connector.connect(**DB_CONFIG)
            print(f"Connected to database: {DB_CONFIG['database']}")
            self._build_item_cache()
        except mysql.connector.Error as err:
            print(f"Error connecting to database: {err}")
            raise
            
    def _build_item_cache(self):
        """Build cache of items and identify duplicates."""
        cursor = self.db_connection.cursor()
        cursor.execute("SELECT entry, name FROM item_template")
        
        items_by_name = {}
        for entry, name in cursor.fetchall():
            self.item_cache[entry] = name
            if name in items_by_name:
                # Mark both items as duplicates
                self.duplicate_items.add(entry)
                self.duplicate_items.add(items_by_name[name])
            else:
                items_by_name[name] = entry
                
        cursor.close()
        print(f"Loaded {len(self.item_cache)} items, found {len(self.duplicate_items)} duplicates")
        self._load_enchantments()
        
    def _load_enchantments(self):
        """Load enchantment data from SpellItemEnchantment.csv"""
        csv_path = Path(__file__).parent / 'SpellItemEnchantment.csv'
        if not csv_path.exists():
            print(f"Warning: {csv_path} not found, enchantment names will not be available")
            return
            
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        enchant_id = int(row['ID'])
                        enchant_name = row['Name_Lang_enUS']
                        if enchant_name and enchant_name.strip():
                            self.enchant_cache[enchant_id] = enchant_name.strip()
                    except (ValueError, KeyError) as e:
                        continue
            print(f"Loaded {len(self.enchant_cache)} enchantments")
        except Exception as e:
            print(f"Error loading enchantments: {e}")
        

    def get_item_name_with_id(self, item_id: int) -> str:
        """Get item name, including ID if it's a duplicate."""
        if item_id not in self.item_cache:
            return f"Unknown Item ({item_id})"
            
        item_name = self.item_cache[item_id]
        
        if item_id in self.duplicate_items:
            return f"{item_name} ({item_id})"
        else:
            return item_name
            
    def format_quantity(self, quantity: int) -> str:
        """Format quantity string."""
        if quantity == 1:
            return ""
        else:
            return f"{quantity}x "
            
    def format_money(self, copper_amount: int) -> str:
        """Format copper amount into gold/silver/copper format."""
        if copper_amount == 0:
            return "0c"
            
        value = copper_amount
        gold = value // 10000
        value = value % 10000
        silver = value // 100
        copper = value % 100
        
        parts = []
        if gold > 0:
            parts.append(f"{gold}g")
        if silver > 0:
            parts.append(f"{silver}s")
        if copper > 0:
            parts.append(f"{copper}c")
            
        # If no parts (shouldn't happen), return the original amount
        if not parts:
            return f"{copper_amount}c"
            
        return " ".join(parts)
            
    def create_comment(self, race_mask: int, class_mask: int, item_id: int, quantity: int, slot_id: int, enchant_id: int = 0) -> str:
        """Create formatted comment string."""
        slot_info = SLOTS.get(slot_id, f'Slot {slot_id}')
        
        # Handle money specifically (item_id = 8 means money)
        if item_id == 8:  # Money
            money_str = self.format_money(quantity)  # quantity is the copper amount
            comment = f"Money: {money_str}"
        else:
            # Handle regular items
            quantity_str = self.format_quantity(quantity)
            item_name = self.get_item_name_with_id(item_id)
            
            # Add enchantment information if present
            if enchant_id and enchant_id in self.enchant_cache:
                enchant_name = self.enchant_cache[enchant_id]
                item_name += f" with Enchantment: {enchant_name}"
            
            comment = f"{quantity_str}{item_name} [{slot_info}]"
        
        # Escape both single and double quotes with backslashes
        comment = comment.replace("\\", "\\\\")
        comment = comment.replace("'", "\\'")
        comment = comment.replace('"', '\\"')
        return comment
        
    def create_backup(self, filepath: str) -> str:
        """Create backup of file with timestamp."""
        timestamp = datetime.now().strftime("%d_%m_%Y_%H_%M_%S")
        
        # Create backup folder on Desktop
        desktop_path = r"C:\Users\Ryan Turner\Desktop"
        backup_folder = os.path.join(desktop_path, f"inventory_backups_{timestamp}")
        os.makedirs(backup_folder, exist_ok=True)
        
        # Get relative path from project root for backup filename
        project_root = Path(__file__).parent
        try:
            rel_path = Path(filepath).relative_to(project_root)
            backup_filename = str(rel_path).replace(os.sep, '_').replace(':', '')
        except ValueError:
            # If file is not relative to project, use just the filename
            backup_filename = os.path.basename(filepath)
            
        backup_path = os.path.join(backup_folder, backup_filename)
        shutil.copy2(filepath, backup_path)
        print(f"Created backup: {backup_path}")
        return backup_path
        
    def find_sql_files(self, data_sql_path: str) -> List[str]:
        """Find all SQL files except uninstall.sql."""
        sql_files = []
        for root, dirs, files in os.walk(data_sql_path):
            for file in files:
                if file.endswith('.sql') and file != 'uninstall.sql':
                    sql_files.append(os.path.join(root, file))
        
        print(f"Found {len(sql_files)} SQL files to process")
        return sql_files
        
    def parse_inventory_insert(self, line: str) -> Optional[Tuple[int, int, int, int, int, int, str]]:
        """Parse an inventory INSERT line to extract values."""
        # Match pattern: (ID, RaceMask, ClassMask, BagID, SlotID, ItemID, Quantity, [Enchant0], ...
        pattern = r'\(\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*([^,]+)(?:,\s*([^,]+))?(?:,\s*(.+))?\)'
        
        match = re.search(pattern, line.strip())
        if not match:
            return None
            
        try:
            id_val = match.group(1).strip()
            race_mask = int(match.group(2).strip())
            class_mask = int(match.group(3).strip())
            slot_id = int(match.group(5).strip())
            item_id = int(match.group(6).strip())
            quantity = int(match.group(7).strip())
            
            # Check if there's an 8th field (Enchant0)
            enchant_id = 0
            if match.group(8) and match.group(8).strip():
                try:
                    # Check if it's a number (enchant) or a quoted string (comment)
                    eighth_field = match.group(8).strip()
                    if not eighth_field.startswith("'"):
                        enchant_id = int(eighth_field)
                except ValueError:
                    pass  # Not a number, probably a comment
            
            return (race_mask, class_mask, slot_id, item_id, quantity, enchant_id, line.strip())
        except (ValueError, IndexError):
            return None
            
    def update_file(self, filepath: str) -> bool:
        """Update comments in a SQL file."""
        print(f"\nProcessing: {filepath}")
        
        # Read file content
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except Exception as e:
            print(f"Error reading file: {e}")
            return False
            
        # Check if file contains mod_ptrtemplate_inventory
        content = ''.join(lines)
        if 'mod_ptrtemplate_inventory' not in content:
            print("  No mod_ptrtemplate_inventory found, skipping")
            return True
            
        # Create backup
        self.create_backup(filepath)
        
        # Process lines
        updated_lines = []
        changes_made = False
        in_inventory_insert = False
        
        for line in lines:
            if 'INSERT INTO `mod_ptrtemplate_inventory`' in line:
                in_inventory_insert = True
                updated_lines.append(line)
                continue
                
            if in_inventory_insert and line.strip().startswith('('):
                # Parse the insert line
                parsed = self.parse_inventory_insert(line)
                if parsed:
                    race_mask, class_mask, slot_id, item_id, quantity, enchant_id, original_line = parsed
                    new_comment = self.create_comment(race_mask, class_mask, item_id, quantity, slot_id, enchant_id)
                    
                    # Replace the comment part - completely overwrite existing comments
                    # Split by comma to get the first 7 fields, then rebuild with new comment
                    stripped_line = line.strip()
                    parts = stripped_line.split(',', 7)  # Split into max 8 parts
                    if len(parts) >= 8:
                        # Check if we have enchant field
                        if enchant_id > 0:
                            # Rebuild with enchant: (ID, RaceMask, ClassMask, BagID, SlotID, ItemID, Quantity, Enchant0, Comment)
                            first_seven = ','.join(parts[:7])
                            new_line = f"{first_seven}, {enchant_id}, '{new_comment}'),\n"
                        else:
                            # Rebuild without enchant: (ID, RaceMask, ClassMask, BagID, SlotID, ItemID, Quantity, Comment)
                            first_seven = ','.join(parts[:7])
                            new_line = f"{first_seven}, '{new_comment}'),\n"
                    else:
                        # Fallback for malformed lines
                        new_line = line
                    
                    updated_lines.append(new_line)
                    changes_made = True
                    enchant_info = f" Enchant:{enchant_id}" if enchant_id > 0 else ""
                    print(f"  Updated: ItemID {item_id} Slot {slot_id}{enchant_info} -> {new_comment}")
                else:
                    updated_lines.append(line)
            else:
                updated_lines.append(line)
                if line.strip() and not line.strip().startswith('(') and in_inventory_insert:
                    in_inventory_insert = False
        
        # Write updated content
        if changes_made:
            try:
                # Fix the last row to end with semicolon
                if updated_lines:
                    for i in range(len(updated_lines) - 1, -1, -1):
                        line = updated_lines[i].strip()
                        if line.startswith('(') and line.endswith('),'):
                            # This is the last INSERT row, change ), to );
                            updated_lines[i] = updated_lines[i].rstrip().rstrip(',') + ';\n'
                            break
                
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.writelines(updated_lines)
                    # Ensure file ends with newline
                    if updated_lines and not updated_lines[-1].endswith('\n'):
                        f.write('\n')
                print(f"  Successfully updated {filepath}")
            except Exception as e:
                print(f"  Error writing file: {e}")
                return False
        else:
            print("  No changes needed")
            
        return True
        
    def process_all_files(self, data_sql_path: str):
        """Process all SQL files in the data/sql directory."""
        if not self.db_connection:
            print("Error: No database connection")
            return
            
        sql_files = self.find_sql_files(data_sql_path)
        
        success_count = 0
        for filepath in sql_files:
            if self.update_file(filepath):
                success_count += 1
                
        print(f"\nProcessing complete: {success_count}/{len(sql_files)} files updated successfully")
        
    def close_connection(self):
        """Close database connection."""
        if self.db_connection:
            self.db_connection.close()
            print("Database connection closed")

def main():
    """Main function."""
    # Get the data/sql path
    script_dir = Path(__file__).parent
    data_sql_path = script_dir / 'data' / 'sql'
    
    if not data_sql_path.exists():
        print(f"Error: Directory {data_sql_path} does not exist")
        return
        
    # Create updater instance
    updater = InventoryCommentUpdater()
    
    try:
        # Connect to database and process files
        updater.connect_to_database()
        updater.process_all_files(str(data_sql_path))
        
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        updater.close_connection()

if __name__ == '__main__':
    main()