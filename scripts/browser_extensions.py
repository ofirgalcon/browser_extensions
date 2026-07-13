#!/usr/local/munkireport/munkireport-python3

import os
import subprocess
import sys
import re
import glob
import json
# import logging

sys.path.insert(0, '/usr/local/munki')
sys.path.insert(0, '/usr/local/munkireport')

from munkilib import FoundationPlist

def _is_plist_mapping(obj):
    """True for Python dicts and Foundation NSDictionary/NSMutableDictionary objects."""
    return hasattr(obj, 'keys') and callable(getattr(obj, 'keys', None))

_CHROMIUM_PROFILE_SETTINGS_CACHE = {}

def _get_chromium_extension_settings(profile_dir):
    """Load Chromium extension settings once per profile directory."""
    if profile_dir in _CHROMIUM_PROFILE_SETTINGS_CACHE:
        return _CHROMIUM_PROFILE_SETTINGS_CACHE[profile_dir]

    combined_settings = {}
    for preferences_file in ("Secure Preferences", "Preferences"):
        preferences_path = os.path.join(profile_dir, preferences_file)
        if not os.path.exists(preferences_path):
            continue

        try:
            with open(preferences_path, 'r') as pref_file:
                preferences = json.loads(pref_file.read())
        except (OSError, ValueError, TypeError):
            continue

        extension_settings = preferences.get('extensions', {}).get('settings', {})
        if not isinstance(extension_settings, dict):
            continue

        for extension_id, extension_data in extension_settings.items():
            if extension_id not in combined_settings and isinstance(extension_data, dict):
                combined_settings[extension_id] = extension_data

    _CHROMIUM_PROFILE_SETTINGS_CACHE[profile_dir] = combined_settings
    return combined_settings

# Configure logging
# logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

def get_users():
    # Get all users' home folders
    cmd = ['/usr/bin/dscl', '.', '-readall', '/Users', 'NFSHomeDirectory']
    proc = subprocess.Popen(cmd, shell=False, bufsize=-1,
                            stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (output, unused_error) = proc.communicate()

    users = []

    for user in output.decode().split('\n'):
        if 'NFSHomeDirectory' in user and '/var/empty' not in user:
            userpath = user.replace("NFSHomeDirectory: ", "")
            # Exclude system and service accounts
            if userpath.startswith('/Users/') and not userpath.startswith('/Users/Shared'):
                users.append(userpath)

    return users

def process_chrome(chrome_extension, user, browser, profile=None):

    try:
        with open(chrome_extension, 'r') as manifest_file:
            extension_manifest = json.loads(manifest_file.read().strip())
    except (OSError, ValueError, TypeError):
        return None
    
    extension_info = {}

    # Much stricter Google detection
    is_google = False
    if extension_manifest.get('id', '').endswith('@google.com'):
        # Only trust extensions with @google.com if they also have a verified Google OAuth2 client ID
        if 'oauth2' in extension_manifest:
            oauth = extension_manifest['oauth2']
            if isinstance(oauth, dict) and 'client_id' in oauth:
                client_id = oauth['client_id']
                if isinstance(client_id, str) and client_id.endswith('.apps.googleusercontent.com'):
                    is_google = True
    
    def clean_and_reorder_name(name):
        """Helper function to clean and reorder names properly"""
        if not name:
            return None
        
        # Split into words and clean each word
        words = name.replace('-', ' ').replace('_', ' ').replace('.', ' ').split()
        words = [w for w in words if w.lower() not in ['extension', 'plugin']]
        
        if not words:
            return None
            
        # Special cases for reordering
        if len(words) >= 2:
            # If first word is 'agent' and there are other words, move it to the end
            if words[0].lower() == 'agent':
                words = words[1:] + [words[0]]
            
        # Capitalize each word
        words = [word.capitalize() for word in words]
        return ' '.join(words)

    # First try to get developer from creator field
    if 'creator' in extension_manifest and extension_manifest['creator']:
        creator = extension_manifest['creator']
        if isinstance(creator, str):
            if '@' in creator:
                # Handle email format like "Name <email@domain.com>"
                if '<' in creator and '>' in creator:
                    extension_info['developer'] = creator.split('<')[0].strip()
                else:
                    # Just use the part before @ if it's a plain email
                    name_part = creator.split('@')[0]
                    if 'superagent' in name_part.lower():
                        extension_info['developer'] = 'superagent'
                    else:
                        clean_name = clean_and_reorder_name(name_part)
                        if clean_name:
                            extension_info['developer'] = clean_name
            else:
                extension_info['developer'] = creator

    # If no developer found yet, check author field
    if 'developer' not in extension_info and 'author' in extension_manifest:
        author_value = extension_manifest['author']
        if isinstance(author_value, list):
            # Try to get a valid developer name from the list
            for value in author_value:
                if isinstance(value, str):
                    clean_name = clean_and_reorder_name(value)
                    if clean_name and clean_name.lower() not in ['plugin', 'agent', 'extension', 'userscripts']:
                        extension_info['developer'] = clean_name
                        break
        elif isinstance(author_value, str):
            if author_value.startswith('__MSG_'):
                # Handle localized author names
                try:
                    locale_file = open(chrome_extension.replace("manifest.json", "_locales/"+extension_manifest['default_locale']+"/messages.json"), 'r')
                    extension_localization = json.loads(locale_file.read().strip())
                    extension_localization_lower = {k.lower():v for k,v in list(extension_localization.items())}
                    local_name = author_value.replace("__MSG_","").replace("__","").lower()
                    author_value = extension_localization_lower[local_name]["message"]
                except:
                    author_value = None

            if author_value:
                # Clean up common unwanted values
                if author_value.lower() in ['plugin', 'agent', 'extension', 'userscripts']:
                    pass
                # Handle email format
                elif '@' in author_value:
                    # Special case for superagent
                    name_part = author_value.split('@')[0]
                    if 'superagent' in name_part.lower():
                        extension_info['developer'] = 'superagent'
                    else:
                        clean_name = clean_and_reorder_name(name_part)
                        if clean_name:
                            extension_info['developer'] = clean_name
                else:
                    # Special case for superagent
                    if 'superagent' in author_value.lower():
                        extension_info['developer'] = 'superagent'
                    else:
                        clean_name = clean_and_reorder_name(author_value)
                        if clean_name:
                            extension_info['developer'] = clean_name

        elif isinstance(author_value, dict):
            # Try different possible fields in the dictionary
            for field in ['name', 'author', 'developer', 'email']:
                if field in author_value and isinstance(author_value[field], str):
                    value = author_value[field]
                    if 'superagent' in value.lower():
                        extension_info['developer'] = 'superagent'
                        break
                    elif value.lower() not in ['plugin', 'agent', 'extension', 'userscripts']:
                        clean_name = clean_and_reorder_name(value)
                        if clean_name:
                            extension_info['developer'] = clean_name
                            break

    for item in extension_manifest:
        if item == "version":
            extension_info['version'] = extension_manifest[item]
        
        elif item in ["author", "developer"]:  # Check both author and developer fields
            # Handle different types of author/developer field
            author_value = extension_manifest[item]
            if isinstance(author_value, list):
                # Lists are not automatically Google anymore
                if any(isinstance(x, str) and x.endswith('@google.com') for x in author_value):
                    is_google = True
                else:
                    # Try to get a valid developer name from the list
                    for value in author_value:
                        if isinstance(value, str):
                            clean_name = clean_and_reorder_name(value)
                            if clean_name and clean_name.lower() not in ['plugin', 'agent', 'extension', 'userscripts']:
                                extension_info['developer'] = clean_name
                                break
            elif isinstance(author_value, str):
                if author_value.startswith('__MSG_'):
                    # Handle localized author names
                    try:
                        locale_file = open(chrome_extension.replace("manifest.json", "_locales/"+extension_manifest['default_locale']+"/messages.json"), 'r')
                        extension_localization = json.loads(locale_file.read().strip())
                        extension_localization_lower = {k.lower():v for k,v in list(extension_localization.items())}
                        local_name = author_value.replace("__MSG_","").replace("__","").lower()
                        author_value = extension_localization_lower[local_name]["message"]
                    except:
                        author_value = None

                if author_value:
                    # Clean up common unwanted values
                    if author_value.lower() in ['plugin', 'agent', 'extension', 'userscripts']:
                        continue
                    # Handle email format
                    if '@' in author_value:
                        if author_value.endswith('@google.com'):  # Must end with @google.com
                            is_google = True
                        else:
                            # Try to extract name from email or use domain
                            name_part = author_value.split('@')[0]
                            # Special case for superagent
                            if 'superagent' in name_part.lower():
                                extension_info['developer'] = 'superagent'
                            else:
                                clean_name = clean_and_reorder_name(name_part)
                                if clean_name:
                                    extension_info['developer'] = clean_name
                    else:
                        # Special case for superagent
                        if 'superagent' in author_value.lower():
                            extension_info['developer'] = 'superagent'
                        else:
                            clean_name = clean_and_reorder_name(author_value)
                            if clean_name:
                                extension_info['developer'] = clean_name

            elif isinstance(author_value, dict):
                # Try different possible fields in the dictionary
                for field in ['name', 'author', 'developer', 'email']:
                    if field in author_value and isinstance(author_value[field], str):
                        value = author_value[field]
                        if value.endswith('@google.com'):  # Must end with @google.com
                            is_google = True
                            break
                        elif 'superagent' in value.lower():
                            extension_info['developer'] = 'superagent'
                            break
                        elif value.lower() not in ['plugin', 'agent', 'extension', 'userscripts']:
                            clean_name = clean_and_reorder_name(value)
                            if clean_name:
                                extension_info['developer'] = clean_name
                                break

        elif item == "description" and extension_manifest[item].startswith('__MSG'):
            try:
                locale_file = open(chrome_extension.replace("manifest.json", "_locales/"+extension_manifest['default_locale']+"/messages.json"), 'r')
                extension_localization = json.loads(locale_file.read().strip())
                extension_localization_lower = {k.lower():v for k,v in list(extension_localization.items())}
                local_name = extension_manifest['description'].replace("__MSG_","").replace("__","").lower()
                extension_info['description'] = extension_localization_lower[local_name]["message"]
            except:
                extension_info['description'] = ""
        elif item == "description":
            extension_info['description'] = extension_manifest[item]

        elif item == "name" and extension_manifest[item].startswith('__MSG'):
            try:
                locale_file = open(chrome_extension.replace("manifest.json", "_locales/"+extension_manifest['default_locale']+"/messages.json"), 'r')
                extension_localization = json.loads(locale_file.read().strip())
                extension_localization_lower = {k.lower():v for k,v in list(extension_localization.items())}
                local_name = extension_manifest['name'].replace("__MSG_","").replace("__","").lower()
                raw_name = extension_localization_lower[local_name]["message"]
                extension_info['name'] = clean_and_reorder_name(raw_name) or raw_name
            except:
                extension_info['name'] = ""
        elif item == "name":
            raw_name = extension_manifest[item]
            extension_info['name'] = clean_and_reorder_name(raw_name) or raw_name

    path_dict = chrome_extension.split('/')
    extension_id = path_dict[-3:][0]
    extension_info['extension_id'] = extension_id
    extension_info['user'] = user
    extension_info['date_installed'] = str(int(os.path.getmtime(chrome_extension)))
    extension_info['browser'] = browser
    
    # Store profile in its own field
    if profile:
        extension_info['profile'] = profile
    
    # Store extension path
    extension_info['extension_path'] = chrome_extension.replace("manifest.json","")
    
    # Set Google as developer only if we're very confident
    if is_google:
        extension_info['developer'] = "Google"
    elif 'developer' not in extension_info:
        # First check for known patterns in the extension name (most reliable method)
        if 'name' in extension_info:
            name = extension_info['name'].lower() if isinstance(extension_info.get('name'), str) else ""
            
            # Check for known patterns
            if 'okta' in name:
                extension_info['developer'] = "Okta"
            # Check for Google
            elif ('google' in name or '(by google)' in name or name.startswith('google ') or name.endswith(' google')):
                extension_info['developer'] = "Google"
            # Check for Gmail, Docs, Sheets
            elif any(x in name for x in ['gmail', 'google docs', 'google sheets']):
                extension_info['developer'] = "Google"
            # Check for Adobe
            elif name.startswith('adobe '):
                extension_info['developer'] = "Adobe"
            # Check for Cisco
            elif name.startswith('cisco '):
                extension_info['developer'] = "Cisco"
        
        # Only if pattern matching fails, try to get developer from homepage URL
        if 'developer' not in extension_info and 'homepage_url' in extension_manifest:
            url = extension_manifest['homepage_url'].lower()
            if 'github.com/' in url:
                # Extract username from GitHub URL
                try:
                    github_user = url.split('github.com/')[1].split('/')[0]
                    if github_user and github_user not in ['topics', 'search']:
                        extension_info['developer'] = github_user
                except:
                    pass

    # Check enabled status from cached profile settings (default True)
    profile_dir = os.path.dirname(os.path.dirname(os.path.dirname(chrome_extension)))
    extension_info['enabled'] = True
    extension_settings = _get_chromium_extension_settings(profile_dir).get(extension_id, {})
    state = extension_settings.get('state') if isinstance(extension_settings, dict) else None
    if state in (0, 1):
        extension_info['enabled'] = state == 1
        
    return extension_info

def process_firefox(firefox_extension, user, firefox_extension_path, profile=None):

    extension_info = {}
    
    # Store extension path
    extension_info['extension_path'] = firefox_extension_path

    # First check defaultLocale for developer info
    if 'defaultLocale' in firefox_extension:
        for locale_item in firefox_extension['defaultLocale']:
            if locale_item == "description" and firefox_extension['defaultLocale'][locale_item]:
                extension_info['description'] = firefox_extension['defaultLocale'][locale_item]
            elif locale_item == "name" and firefox_extension['defaultLocale'][locale_item]:
                name = firefox_extension['defaultLocale'][locale_item]
                extension_info['name'] = name
                # Special case for 1Password
                if '1password' in name.lower():
                    extension_info['developer'] = "1Password"
            elif locale_item == "creator" and firefox_extension['defaultLocale'][locale_item] and 'developer' not in extension_info:
                # Handle email format: "Name <email@domain.com>"
                creator = firefox_extension['defaultLocale'][locale_item]
                if isinstance(creator, str):
                    # Special case for 1Password
                    if 'agilebits' in creator.lower() or '1password' in creator.lower():
                        extension_info['developer'] = "1Password"
                    elif '<' in creator and '>' in creator:
                        extension_info['developer'] = creator.split('<')[0].strip()
                    else:
                        extension_info['developer'] = creator
            elif locale_item == "homepageURL" and 'developer' not in extension_info:
                homepage = firefox_extension['defaultLocale'][locale_item]
                if homepage and isinstance(homepage, str) and 'github.com/' in homepage.lower():
                    try:
                        github_user = homepage.split('github.com/')[1].split('/')[0]
                        if github_user and github_user not in ['topics', 'search']:
                            extension_info['developer'] = github_user
                    except:
                        pass

    # If no developer found in defaultLocale, check other locations
    if 'developer' not in extension_info:
        # First priority: Check for known patterns in the extension name
        if 'name' in extension_info:
            name = extension_info['name'].lower() if isinstance(extension_info.get('name'), str) else ""
            
            # Check for known patterns
            if 'okta' in name:
                extension_info['developer'] = "Okta"
            elif ('google' in name or '(by google)' in name or name.startswith('google ') or name.endswith(' google')):
                extension_info['developer'] = "Google"
            elif any(x in name for x in ['gmail', 'google docs', 'google sheets']):
                extension_info['developer'] = "Google"
            elif name.startswith('adobe '):
                extension_info['developer'] = "Adobe"
            elif name.startswith('cisco '):
                extension_info['developer'] = "Cisco"
        
        # Second priority: Check creator/developer/author fields directly
        if 'developer' not in extension_info:
            for field in ['creator', 'developer', 'author']:
                if field in firefox_extension and firefox_extension[field]:
                    if isinstance(firefox_extension[field], str):
                        if '<' in firefox_extension[field] and '>' in firefox_extension[field]:
                            extension_info['developer'] = firefox_extension[field].split('<')[0].strip()
                        else:
                            extension_info['developer'] = firefox_extension[field]
                        break
                    elif isinstance(firefox_extension[field], dict) and 'name' in firefox_extension[field]:
                        extension_info['developer'] = firefox_extension[field]['name']
                        break

        # Third priority: Try to get from extension ID if still no developer name found
        if 'developer' not in extension_info and 'id' in firefox_extension:
            ext_id = firefox_extension['id']
            if '@' in ext_id:
                try:
                    # Extract developer from email format
                    developer = ext_id.split('@')[0]
                    if developer and developer.lower() not in ['addon', 'extension', 'firefox', 'mozilla', 'plugin', 'plugiin']:
                        # Convert dashes/underscores to spaces and capitalize
                        developer = ' '.join(word.capitalize() for word in developer.replace('-', ' ').replace('_', ' ').split())
                        extension_info['developer'] = developer
                except:
                    pass
            elif '.' in ext_id:
                # Try to extract organization name from ID
                parts = ext_id.split('.')
                filtered_parts = [p for p in parts if p.lower() not in ['com', 'org', 'net', 'addon', 'extension', 'firefox', 'mozilla', 'plugin', 'plugiin']]
                if filtered_parts:
                    # Convert dashes/underscores to spaces and capitalize
                    developer = ' '.join(word.capitalize() for word in filtered_parts[0].replace('-', ' ').replace('_', ' ').split())
                    extension_info['developer'] = developer

        # Check if it's a Mozilla extension as last resort
        if 'developer' not in extension_info:
            is_mozilla = False
            if 'homepageURL' in firefox_extension:
                if 'mozilla.com' in firefox_extension['homepageURL'].lower() or 'mozilla.org' in firefox_extension['homepageURL'].lower():
                    is_mozilla = True
            if 'id' in firefox_extension and ('@mozilla' in firefox_extension['id'].lower() or 'mozilla@' in firefox_extension['id'].lower()):
                is_mozilla = True
            if is_mozilla:
                extension_info['developer'] = "Mozilla"

    # Process other standard fields
    for item in firefox_extension:
        if item == "version":
            extension_info['version'] = firefox_extension[item]
        elif item == "active":
            extension_info['enabled'] = firefox_extension[item]
        elif item == "installDate" or item == "updateDate":
            extension_info['date_installed'] = str(firefox_extension[item]/1000)
        elif item == "id":
            extension_info['extension_id'] = firefox_extension[item]
        elif item == "path":
            if firefox_extension[item] is None:
                extension_info['extension_path'] = firefox_extension_path.replace("extensions.json","")
            else:
                extension_info['extension_path'] = firefox_extension[item]

    extension_info['user'] = user
    extension_info['browser'] = "Firefox"
    
    # Store profile in its own field
    if profile:
        extension_info['profile'] = profile
    
    # Ensure date_installed is always set (use file modification time as fallback)
    if 'date_installed' not in extension_info:
        extension_info['date_installed'] = str(int(os.path.getmtime(firefox_extension_path)))
    
    return extension_info

def process_safari(safari_plist_path, user):
    """Process Safari extensions from the Extensions.plist file"""
    
    extensions_list = []
    
    try:
        # Read the plist file - handle the specific "stream had too few bytes" error
        try:
            safari_extensions = FoundationPlist.readPlist(safari_plist_path)
        except Exception as read_error:
            # If we get the specific "stream had too few bytes" error, just return empty list without logging
            # Convert error to string first to handle Objective-C bridge types (OC_PythonLong, etc.)
            # tested with python 3.12.1
            # For OC_PythonLong errors, just return empty list silently
            try:
                # Check error type first - but be defensive about using 'in' operator
                try:
                    error_type = type(read_error).__name__
                    # Check if error type name contains OC_PythonLong - use try/except for safety
                    try:
                        if isinstance(error_type, str) and ("OC_PythonLong" in error_type or "PythonLong" in error_type):
                            # OC_PythonLong error - just return empty, don't try to inspect it
                            return extensions_list
                    except TypeError:
                        # Can't use 'in' operator - likely OC_PythonLong, return empty
                        return extensions_list
                except Exception:
                    # If even getting the type name fails, return empty
                    return extensions_list
                
                # Try to safely convert error to string
                if isinstance(read_error, str):
                    error_str = read_error
                else:
                    try:
                        error_str = str(read_error)
                        # Verify it's actually a string
                        if not isinstance(error_str, str):
                            # Not a real string - likely OC_PythonLong, return empty
                            return extensions_list
                    except (TypeError, AttributeError, ValueError):
                        # Can't convert - likely OC_PythonLong, return empty
                        return extensions_list
                
                # Now safely check if string contains the error message
                if isinstance(error_str, str):
                    try:
                        # Use 'in' operator - catch TypeError if error_str is OC_PythonLong
                        if "stream had too few bytes" in error_str:
                            return extensions_list
                    except (TypeError, AttributeError):
                        # OC_PythonLong - can't use 'in' operator, just return empty
                        return extensions_list
            except Exception:
                # If anything fails, just return empty list
                # This handles all Objective-C bridge type issues
                return extensions_list
            # For other errors, don't re-raise - just return empty list to continue processing
            return extensions_list
        
        # Process each extension in the plist
        if not _is_plist_mapping(safari_extensions):
            return extensions_list

        for extension_id, extension_data in safari_extensions.items():
            # Some Safari plist entries can be Objective-C bridged scalar values
            # (for example OC_PythonLong). Skip anything that is not a mapping.
            if not _is_plist_mapping(extension_data):
                continue

            extension_info = {}
            
            # Keep the original extension ID
            extension_info['extension_id'] = extension_id
            
            # Extract name from the key (e.g., com.example.extension -> Example)
            extension_id_str = str(extension_id)
            clean_id = extension_id_str.split(' ')[0].split('(')[0]
            name_parts = clean_id.split('.')[:-1]  # Ignore the last part

            # Try to get the extension name first
            # Remove specific words
            unwanted_words = {'com', 'org', 'mac', 'macos', 'extension', 'safari'}
            filtered_name_parts = [part for part in name_parts if part.lower() not in unwanted_words]
            
            # Remove duplicate words (case insensitive)
            seen_words = set()
            unique_parts = []
            for part in filtered_name_parts:
                if part.lower() not in seen_words:
                    seen_words.add(part.lower())
                    unique_parts.append(part)
            
            extension_name = ' '.join(unique_parts).replace('-', ' ')
            
            # Capitalize each word in the name
            extension_info['name'] = ' '.join(word.capitalize() for word in extension_name.split())
            
            # Handle special cases for known extensions
            if 'lastpass' in extension_info['name'].lower() and 'macdesktop' in extension_info['name'].lower():
                extension_info['name'] = 'LastPass'
            elif 'cisco' in extension_info['name'].lower() and 'webex' in extension_info['name'].lower() and 'start' in extension_info['name'].lower():
                extension_info['name'] = 'Cisco Webex'
            
            # Remove duplicate words in the final name (e.g., "Todoist Todoist" -> "Todoist")
            if extension_info['name']:
                name_words = extension_info['name'].split()
                if len(name_words) > 1:
                    # Check for exact duplicates (case-sensitive)
                    if len(set(name_words)) < len(name_words):
                        unique_words = []
                        seen_words = set()
                        for word in name_words:
                            if word.lower() not in seen_words:
                                seen_words.add(word.lower())
                                unique_words.append(word)
                        extension_info['name'] = ' '.join(unique_words)
            
            # Now handle the developer name with the correct priority:
            # 1. Check for pattern matches first (more reliable than ID-based extraction)
            name = extension_info['name'].lower() if 'name' in extension_info else ""
            developer_found = False
            
            # Check for known patterns
            if 'okta' in name:
                extension_info['developer'] = "Okta"
                developer_found = True
            elif ('google' in name or '(by google)' in name or name.startswith('google ') or name.endswith(' google')):
                extension_info['developer'] = "Google"
                developer_found = True
            elif any(x in name for x in ['gmail', 'google docs', 'google sheets']):
                extension_info['developer'] = "Google"
                developer_found = True
            elif name.startswith('adobe '):
                extension_info['developer'] = "Adobe"
                developer_found = True
            elif name.startswith('cisco '):
                extension_info['developer'] = "Cisco"
                developer_found = True
            elif 'lastpass' in name:
                extension_info['developer'] = "LastPass"
                developer_found = True
            elif 'todoist' in name:
                extension_info['developer'] = "Doist"
                developer_found = True
            
            # 2. Only if pattern matching fails, try to extract from ID as last resort
            if not developer_found and len(name_parts) > 1:
                for part in name_parts[1:]:  # Start from second part
                    if part.lower() not in ['com', 'org', 'userscripts', 'net', 'app', 'extension', 'chrome', 'plugin', 'plugiin']:
                        extension_info['developer'] = part.capitalize()
                        developer_found = True
                        break
            
            # Check if extension is enabled
            if 'Enabled' in extension_data:
                extension_info['enabled'] = extension_data['Enabled']
            
            # Get installation date
            if 'AddedDate' in extension_data:
                # Convert date to timestamp
                try:
                    # For __NSTaggedDate objects, convert to string first
                    date_obj = extension_data['AddedDate']
                    if hasattr(date_obj, 'timeIntervalSince1970'):
                        # Use timeIntervalSince1970 method if available
                        extension_info['date_installed'] = str(int(date_obj.timeIntervalSince1970()))
                    elif hasattr(date_obj, 'strftime'):
                        # If it has strftime, use it to get timestamp
                        import time
                        extension_info['date_installed'] = str(int(time.mktime(date_obj.strftime("%Y-%m-%d %H:%M:%S"))))
                    else:
                        # Convert to string and parse
                        import time
                        import datetime
                        date_str = str(date_obj)
                        try:
                            # Try to parse ISO format date string
                            dt = datetime.datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S %z")
                            extension_info['date_installed'] = str(int(time.mktime(dt.timetuple())))
                        except:
                            # If all else fails, use file modification time
                            extension_info['date_installed'] = str(int(os.path.getmtime(safari_plist_path)))
                except:
                    # Use file modification time as fallback
                    extension_info['date_installed'] = str(int(os.path.getmtime(safari_plist_path)))
            else:
                # Use file modification time if no date is available
                extension_info['date_installed'] = str(int(os.path.getmtime(safari_plist_path)))
            
            # Set browser and user info
            extension_info['browser'] = "Safari"
            extension_info['user'] = user
            
            # Add description based on WebsiteAccess information if available
            description = ""
            if 'WebsiteAccess' in extension_data and _is_plist_mapping(extension_data['WebsiteAccess']):
                website_access = extension_data['WebsiteAccess']
                if 'Level' in website_access:
                    access_level = website_access['Level']
                    description += f"Access Level: {access_level}. "
                
                if 'Has Injected Content' in website_access:
                    has_injected = website_access['Has Injected Content']
                    if has_injected:
                        description += "Can inject content into websites. "
                
                if 'Allowed Domains' in website_access and website_access['Allowed Domains']:
                    domains = website_access['Allowed Domains']
                    if domains:
                        description += f"Allowed on {len(domains)} specific domains."
            
            # If we have permission information, add it to the description
            if 'GrantedPermissionOrigins' in extension_data and extension_data['GrantedPermissionOrigins']:
                permissions = extension_data['GrantedPermissionOrigins']
                if permissions:
                    if description:
                        description += " "
                    description += f"Has {len(permissions)} granted permissions."
            
            # If we still don't have a description, use a generic one
            if not description:
                description = "Safari extension"
            
            extension_info['description'] = description
            
            # Add to the list
            extensions_list.append(extension_info)
            
    except Exception as e:
        # Only log serious errors, not just empty files
        # Convert error to string first to handle Objective-C bridge types (OC_PythonLong, etc.)
        try:
            # Safely convert error to string - handle OC_PythonLong
            if isinstance(e, str):
                error_str = e
            else:
                # Try to convert to string, but handle OC_PythonLong specially
                try:
                    error_str = str(e)
                    # Check if str() returned an OC_PythonLong (it won't be a real string)
                    if not isinstance(error_str, str):
                        # OC_PythonLong - can't check contents, just log type
                        print(f"Error processing Safari extensions: {type(e).__name__}")
                        return extensions_list
                except (TypeError, AttributeError, ValueError):
                    print(f"Error processing Safari extensions: {type(e).__name__}")
                    return extensions_list
            
            # Now safely check if string contains the error message
            if isinstance(error_str, str):
                try:
                    # Use 'in' operator - catch TypeError if error_str is OC_PythonLong
                    if "stream had too few bytes" not in error_str:
                        # Use string concatenation instead of f-string to avoid OC_PythonLong issues
                        try:
                            print("Error processing Safari extensions: " + str(error_str))
                        except Exception:
                            # If printing fails, skip - likely OC_PythonLong issue
                            pass
                except (TypeError, AttributeError):
                    # OC_PythonLong - can't use 'in' operator, skip logging
                    pass
        except (TypeError, AttributeError, ValueError):
            # If we can't convert the error to string, just log a generic message
            print(f"Error processing Safari extensions: {type(e).__name__}")
    
    return extensions_list

def process_browsers(users):

    if users == "":
        return []

    # First collect all extensions with deduplication for Chrome, Edge, and Firefox
    unique_extensions = {}
    
    for user in users:

        # Check for Chrome extensions in all profiles
        chrome_base_path = user+"/Library/Application Support/Google/Chrome/"
        if os.path.isdir(chrome_base_path):
            # Get all profile directories (Default and any named profiles)
            chrome_profiles = [d for d in os.listdir(chrome_base_path) 
                              if os.path.isdir(os.path.join(chrome_base_path, d)) 
                              and (d == "Default" or d.startswith("Profile"))]
            
            for profile in chrome_profiles:
                chrome_extension_path = os.path.join(chrome_base_path, profile, "Extensions")
                if os.path.isdir(chrome_extension_path):
                    # Fix the glob pattern by adding a trailing slash and proper path joining
                    for chrome_extension in glob.glob(os.path.join(chrome_extension_path, "*", "*", "manifest.json")):
                        profile_info = "Default" if profile == "Default" else profile
                        extension_data = process_chrome(chrome_extension, user.replace("/Users/",""), "Google Chrome", profile_info)
                        if not extension_data:
                            continue
                        
                        # Create a unique key for this extension
                        unique_key = f"{extension_data['user']}|{extension_data['browser']}|{extension_data['profile']}|{extension_data['extension_id']}"
                        
                        # Only add if we haven't seen this extension before, or if it's newer
                        # Handle missing date_installed field gracefully
                        current_date = extension_data.get('date_installed', '0')
                        existing_date = unique_extensions.get(unique_key, {}).get('date_installed', '0')
                        
                        if unique_key not in unique_extensions or int(float(current_date)) > int(float(existing_date)):
                            unique_extensions[unique_key] = extension_data

        # Check for Edge extensions in all profiles
        edge_base_path = user+"/Library/Application Support/Microsoft Edge/"
        if os.path.isdir(edge_base_path):
            # Get all profile directories (Default and any named profiles)
            edge_profiles = [d for d in os.listdir(edge_base_path) 
                            if os.path.isdir(os.path.join(edge_base_path, d)) 
                            and (d == "Default" or d.startswith("Profile"))]
            
            for profile in edge_profiles:
                edge_extension_path = os.path.join(edge_base_path, profile, "Extensions")
                if os.path.isdir(edge_extension_path):
                    # Fix the glob pattern by adding a trailing slash and proper path joining
                    for edge_extension in glob.glob(os.path.join(edge_extension_path, "*", "*", "manifest.json")):
                        profile_info = "Default" if profile == "Default" else profile
                        extension_data = process_chrome(edge_extension, user.replace("/Users/",""), "Microsoft Edge", profile_info)
                        if not extension_data:
                            continue
                        
                        # Create a unique key for this extension
                        unique_key = f"{extension_data['user']}|{extension_data['browser']}|{extension_data['profile']}|{extension_data['extension_id']}"
                        
                        # Only add if we haven't seen this extension before, or if it's newer
                        # Handle missing date_installed field gracefully
                        current_date = extension_data.get('date_installed', '0')
                        existing_date = unique_extensions.get(unique_key, {}).get('date_installed', '0')
                        
                        if unique_key not in unique_extensions or int(float(current_date)) > int(float(existing_date)):
                            unique_extensions[unique_key] = extension_data

        # Check for Brave extensions in all profiles
        brave_base_path = user+"/Library/Application Support/BraveSoftware/Brave-Browser/"
        if os.path.isdir(brave_base_path):
            # Get all profile directories (Default and any named profiles)
            brave_profiles = [d for d in os.listdir(brave_base_path)
                             if os.path.isdir(os.path.join(brave_base_path, d))
                             and (d == "Default" or d.startswith("Profile"))]

            for profile in brave_profiles:
                brave_extension_path = os.path.join(brave_base_path, profile, "Extensions")
                if os.path.isdir(brave_extension_path):
                    for brave_extension in glob.glob(os.path.join(brave_extension_path, "*", "*", "manifest.json")):
                        profile_info = "Default" if profile == "Default" else profile
                        extension_data = process_chrome(brave_extension, user.replace("/Users/",""), "Brave", profile_info)
                        if not extension_data:
                            continue

                        # Create a unique key for this extension
                        unique_key = f"{extension_data['user']}|{extension_data['browser']}|{extension_data['profile']}|{extension_data['extension_id']}"

                        # Only add if we haven't seen this extension before, or if it's newer
                        # Handle missing date_installed field gracefully
                        current_date = extension_data.get('date_installed', '0')
                        existing_date = unique_extensions.get(unique_key, {}).get('date_installed', '0')

                        if unique_key not in unique_extensions or int(float(current_date)) > int(float(existing_date)):
                            unique_extensions[unique_key] = extension_data

        # Check for Firefox extensions
        firefox_path = user+"/Library/Application Support/Firefox/Profiles/"
        if os.path.isdir(firefox_path):
            for firefox_extension_json_path in glob.glob(firefox_path+'*/extensions.json'):
                # Extract profile name from path
                profile_name = firefox_extension_json_path.split('/')[-2]
                firefox_extension_json = json.loads(open(firefox_extension_json_path, 'r').read().strip())
                for firefox_extension in firefox_extension_json['addons']:
                    extension_data = process_firefox(firefox_extension, user.replace("/Users/",""), firefox_extension_json_path, profile_name)
                    
                    # Create a unique key for this extension
                    unique_key = f"{extension_data['user']}|{extension_data['browser']}|{extension_data['profile']}|{extension_data['extension_id']}"
                    
                    # Only add if we haven't seen this extension before, or if it's newer
                    # Handle missing date_installed field gracefully
                    current_date = extension_data.get('date_installed', '0')
                    existing_date = unique_extensions.get(unique_key, {}).get('date_installed', '0')
                    
                    if unique_key not in unique_extensions or int(float(current_date)) > int(float(existing_date)):
                        unique_extensions[unique_key] = extension_data

        # Check for Safari extensions - check multiple possible locations
        safari_extension_paths = [
            user+"/Library/Containers/com.apple.Safari/Data/Library/Safari/AppExtensions/Extensions.plist",
            user+"/Library/Containers/com.apple.Safari/Data/Library/Safari/WebExtensions/Extensions.plist",
            user+"/Library/Safari/Extensions/Extensions.plist"
        ]

        for safari_extension_path in safari_extension_paths:
            if os.path.isfile(safari_extension_path):
                try:
                    safari_extensions = process_safari(safari_extension_path, user.replace("/Users/",""))
                    # Add profile field for consistency with our new approach
                    for extension in safari_extensions:
                        extension['profile'] = "Default"
                    # Add Safari extensions to the unique extensions dictionary
                    for extension in safari_extensions:
                        # Create a unique key for this extension
                        unique_key = f"{extension['user']}|{extension['browser']}|{extension['profile']}|{extension['extension_id']}"
                        # Only add if we haven't seen this extension before, or if it's newer
                        # Handle missing date_installed field gracefully
                        current_date = extension.get('date_installed', '0')
                        existing_date = unique_extensions.get(unique_key, {}).get('date_installed', '0')
                        
                        if unique_key not in unique_extensions or int(float(current_date)) > int(float(existing_date)):
                            unique_extensions[unique_key] = extension
                except Exception as e:
                    # Log errors for debugging (but continue processing other paths)
                    # Note: Safari extensions require Full Disk Access permissions
                    # If you see errors here, grant Full Disk Access to munkireport-python3
                    # tested with python 3.12.1
                    # Note: OC_PythonLong errors are harmless - they occur when FoundationPlist
                    # raises an exception with OC_PythonLong objects. We silently skip these.
                    import sys
                    # Silently skip OC_PythonLong errors - they're harmless
                    # The error "argument of type 'OC_PythonLong' is not iterable" occurs
                    # when we try to inspect the exception object. We catch and ignore it.
                    # Use a very simple approach - just try to get error type name, don't inspect the message
                    try:
                        error_type_name = type(e).__name__
                        # Only log if it's not a known OC_PythonLong issue
                        # Don't try to convert to string or check contents - that triggers the error
                        if error_type_name not in ['TypeError', 'AttributeError']:
                            # Might be a real error - try to log just the type
                            try:
                                print("Error processing Safari extensions from " + str(safari_extension_path) + ": " + error_type_name, file=sys.stderr)
                            except Exception:
                                # If even this fails, skip - likely OC_PythonLong issue
                                pass
                    except Exception:
                        # If anything fails in error handling, just skip - likely OC_PythonLong issue
                        # This prevents infinite recursion of error handling
                        pass

    # Convert the dictionary of unique extensions to a list
    out = list(unique_extensions.values())
    return out

def main():
    """Main"""

    # Get information about the browser extensions
    users = get_users()
    result = process_browsers(users)

    # Write browser extensions to cache
    cachedir = '%s/cache' % os.path.dirname(os.path.realpath(__file__))
    output_plist = os.path.join(cachedir, 'browser_extensions.plist')
    FoundationPlist.writePlist(result, output_plist)
    #print FoundationPlist.writePlistToString(result)

if __name__ == "__main__":
    main()
