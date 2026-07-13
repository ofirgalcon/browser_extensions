Browser Extensions module
==============

Browser extensions module for MunkiReport. Reports on users' installed extensions for Firefox, Google Chrome, Microsoft Edge, Brave, and Safari. 

### Configuration Options

The module provides configuration options to filter out unwanted browser extensions from your reports. By default, common system extensions for Firefox, Google Chrome, Microsoft Edge, and Brave are not reported.

#### Environment Variables Configuration

To customize which extensions are filtered out, add the following variables to your `.env` file.
Filters are exact match based (`ID` exact match, `Name` case-insensitive exact match):

```
# Filter extensions by ID (comma-separated list of extension IDs)
BROWSER_EXTENSION_ID_IGNORELIST=["extension_id_1","extension_id_2"]

# Filter extensions by name (comma-separated list of extension names)
BROWSER_EXTENSION_NAME_IGNORELIST=["Extension Name 1","Extension Name 2"]
```

#### Default Ignored Extensions

The module comes pre-configured to ignore common system extensions:

- Chrome Web Store Payments (`nmmhkkegccagdldgiimedpiccmgmieda`)
- Chrome Media Router (`pkedcjkdefgpdelpbcmbmeomcjbeemfm`)
- Brave built-in extension (`mnojpmjdmbbfmejpflffifhffcmidifd`)
- Brave CRLSet component (`hfnkpimlhhgieaddgfemjhofmfblmnib`)
- Various Firefox system add-ons (e.g., `default-theme@mozilla.org`, `screenshots@mozilla.org`)

### Safari Extensions Permissions

Safari extensions may not be available on all systems due to permission restrictions. To enable Safari extension reporting:

1. **Full Disk Access**: Grant Full Disk Access to the MunkiReport Python executable:
   - Open System Preferences/Settings > Security & Privacy/Privacy > Full Disk Access
   - Add `/usr/local/munkireport/munkireport-python3` to the list of allowed applications

2. **MDM Configuration**: For managed devices, you can use an MDM solution to grant the necessary permissions:
   - Create a Privacy Preferences Policy Control (PPPC) profile
   - Allow Full Disk Access for `/usr/local/munkireport/munkireport-python3`
   - Deploy the profile to your managed devices

These permissions are required because Safari extensions are stored in protected locations that require special access privileges to read.

### Features

* Displays browser extensions organized alphabetically by browser type (Chrome, Edge, Brave, Firefox, Safari)
* Extensions within each browser category are sorted alphabetically by name
* Supports browser profiles, showing which profile each extension belongs to
* Deduplicates extensions to avoid showing the same extension multiple times
* Shows detailed information about each extension including version, installation date, and description
* Tracks extension installation paths for troubleshooting and management
* Brave data is collected from Chromium-style profile folders (`~/Library/Application Support/BraveSoftware/Brave-Browser/...`) as documented in Brave's official project wiki: [Brave-Country-Id](https://github.com/brave/brave-browser/wiki/Brave-Country-Id)

Table Schema
-----

Database:
* name - varchar(255) - name of extension
* extension_id - varchar(255) - extension ID
* version - varchar(255) - extension version
* description - text - extension's description
* browser - varchar(255) - Firefox, Google Chrome, Microsoft Edge, Brave, or Safari
* profile - varchar(255) - browser profile that contains the extension (e.g., Default, Profile 1)
* date_installed - bigint - date extension was updated/installed
* developer - varchar(255) - name of extension developer, Firefox only
* enabled - boolean - If extension is enabled, Firefox only
* user - varchar(255) - user profile that contains extension
* extension_path - text - file system path to the extension files
