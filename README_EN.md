# C Drive Large File Migration Tool

## Project Overview

This tool is designed to migrate large folders (over 1GB) from the C drive's Program Files and User/{username}/AppData directories to a target path, and create symbolic links in the original C drive locations. This helps free up disk space on the C drive while ensuring programs continue to function normally through compression, migration, and decompression methods.

## Features

1. **Smart Scanning**: Scan specified directories for folders exceeding a specified size, with customizable scan paths and depths
2. **Folder Filtering**: Support for global and path-specific folder exclusion lists to avoid migrating critical system files
3. **Resource Limiting**: Configurable CPU and memory usage limits to ensure the migration process doesn't affect normal system operation
4. **Compressed Migration**: Compress large folders before migrating to the target path and decompress them, ensuring data integrity
5. **Smart Cleanup**: Remove folders from the original C drive path, automatically handle file occupation issues, with multiple retry support
6. **Symbolic Link Creation**: Create symbolic links at the original paths pointing to the new locations, maintaining normal program operation
7. **Graphical Interface**: Intuitive graphical interface with detailed logs and progress information
8. **Multi-threading**: Automatically optimize thread count to improve execution efficiency
9. **Path Mapping Records**: Save path mappings before and after migration for easy management and recovery

## System Requirements

- Windows operating system
- Python 3.6+
- Administrator privileges (required for creating symbolic links)
- Sufficient space on the target disk

## Quick Start

### Method 1: Using Batch File (Recommended)

1. Double-click the `start_migrate_tool.bat` file
2. The system will automatically request administrator privileges and start the program
3. If necessary dependencies are missing, the program will install them automatically

### Method 2: Manual Start (Traditional Method)

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Run Command Prompt or PowerShell as administrator
3. Navigate to the project directory
4. Run the following command:

```bash
python main.py
```

## Creating Executable File

If you want to package the program as a standalone executable file, you can follow these steps:

1. Run the packaging script:

```bash
python build.py
```

2. After packaging is complete, the executable file will be located in the `dist/MigrateC` directory
3. Double-click `MigrateC.exe` to start the program without needing to install Python environment

## Configuration

The project uses a `config.yaml` file for configuration. Main configuration items include:

### Scan Configuration

```yaml
scan:
  # List of directories to scan and their corresponding scan levels
  scan_paths:
    - path: "C:\Users\%USERNAME%\AppData"
      max_depth: 2          # Folder depth to query in this path
      exclude_folders: []   # List of specific folder names to exclude in this path
    - path: "C:\Program Files"
      max_depth: 1
      exclude_folders: ["Common Files", "Microsoft", "WindowsApps"]
  # File size threshold (in bytes, 1GB = 1073741824 bytes)
  size_threshold: 1073741824
  # Global list of folder names to exclude
  exclude_folders: ["Windows", "System32", "ProgramData"]
  # Scan results output file path
  output_file: "./output/scan_results.json"
```

### Migration Configuration

```yaml
migration:
  # Target disk path
  target_path: "D:\C_backup"
  # Temporary storage path for compressed files
  temp_path: "./temp"
  # Mapping file output path
  mapping_file: "./output/path_mapping.json"
```

### Performance Configuration

```yaml
performance:
  # Maximum number of threads, set to 0 for automatic determination
  max_threads: 0
  # CPU usage limit (between 0-1, representing the proportion of CPU cores that can be used)
  cpu_limit: 0.5
  # Memory usage limit (between 0-1, representing the proportion of system memory that can be used)
  memory_limit: 0.5
```

## Usage

### Run as Administrator

Since creating symbolic links requires administrator privileges, please run the program as an administrator:

1. Right-click on Command Prompt or PowerShell, select "Run as administrator"
2. Navigate to the project directory
3. Run the following command:

```bash
python main.py
```

### Graphical Interface Operation

1. **Scan**: Click the "Scan" button to start scanning for large folders; scan results will be displayed in the log area
2. **Migrate**: Click the "Migrate" button to start migrating large folders to the target path
3. **Clean**: Click the "Clean" button to delete folders from the original C drive path
4. **Link**: Click the "Create Links" button to create symbolic links at the original paths
5. **One-click Operation**: Click the "Complete All" button to automatically perform scanning, migration, cleaning, and link creation
6. **Cancel**: Click the "Cancel" button to cancel the current operation

## Workflow

1. **Scanning Phase**: Scan specified directories to find folders exceeding the specified size
2. **Migration Phase**: Compress large folders, migrate them to the target path, and decompress
3. **Cleaning Phase**: Delete folders from the original C drive path, handling file occupation issues
4. **Linking Phase**: Create symbolic links at the original paths pointing to the new locations

## Frequently Asked Questions

### 1. Why are administrator privileges required?

Creating symbolic links requires administrator privileges due to Windows system security restrictions.

### 2. Will original programs still work normally after migration?

Yes. Symbolic links are transparent to programs, which will access the links as if accessing the original paths, without perceiving that files are actually stored elsewhere.

### 3. How to restore the pre-migration state?

You can manually copy folders from the target path back to the original paths and delete the symbolic links. You can also refer to the path mappings recorded in the `output/path_mapping.json` file for restoration.

### 4. What if the migration process is interrupted?

The program records completed migrations; running the program again will continue unfinished migrations.

### 5. How to customize scan paths and size thresholds?

Modify the `scan.scan_paths` and `scan.size_threshold` configuration items in the `config.yaml` file.

## Notes

1. Ensure the target disk has sufficient space before migration
2. It's recommended to back up important data before migration
3. Do not migrate critical system folders, as this may cause system instability
4. The migration process may take a long time; please be patient
5. If files cannot be deleted, it may be because they are in use; the program will automatically retry

## License

[MIT License](LICENSE)

## Contributions

Issues and improvement suggestions are welcome!