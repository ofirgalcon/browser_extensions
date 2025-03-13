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

# Configure logging
# logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

def get_users():
    # Get all users' home folders
    cmd = ['dscl', '.', '-readall', '/Users', 'NFSHomeDirectory']
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

    extension_manifest = json.loads(open(chrome_extension, 'r').read().strip())
    
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

    # Check for enabled status in Preferences files
    try:
        # Determine the profile directory path
        profile_dir = os.path.dirname(os.path.dirname(os.path.dirname(chrome_extension)))
        
        # Default to enabled if we can't determine the state
        extension_info['enabled'] = True
        
        # Try to read Secure Preferences file first (more likely to contain extension state)
        secure_preferences_path = os.path.join(profile_dir, "Secure Preferences")
        if os.path.exists(secure_preferences_path):
            with open(secure_preferences_path, 'r') as f:
                secure_preferences = json.loads(f.read())
                # Check if extension settings exist
                if ('extensions' in secure_preferences and 
                    'settings' in secure_preferences['extensions'] and 
                    extension_id in secure_preferences['extensions']['settings']):
                    if 'state' in secure_preferences['extensions']['settings'][extension_id]:
                        # State is 1 for enabled, 0 for disabled
                        extension_info['enabled'] = secure_preferences['extensions']['settings'][extension_id]['state'] == 1
                    # If state is not found, keep the default (True)
        
        # If not found in Secure Preferences, try regular Preferences
        if extension_info['enabled'] is True:  # Only check if we haven't found a disabled state
            preferences_path = os.path.join(profile_dir, "Preferences")
            if os.path.exists(preferences_path):
                with open(preferences_path, 'r') as f:
                    preferences = json.loads(f.read())
                    # Check if extension settings exist
                    if ('extensions' in preferences and 
                        'settings' in preferences['extensions'] and 
                        extension_id in preferences['extensions']['settings']):
                        if 'state' in preferences['extensions']['settings'][extension_id]:
                            # State is 1 for enabled, 0 for disabled
                            extension_info['enabled'] = preferences['extensions']['settings'][extension_id]['state'] == 1
                        # If state is not found, keep the default (True)
    except Exception as e:
        # Default to True if there's any error reading the preferences
        extension_info['enabled'] = True
        
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
                if 'github.com/' in homepage.lower():
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
            if "stream had too few bytes" in str(read_error):
                return extensions_list
            # Otherwise, re-raise the exception
            raise
        
        # Process each extension in the plist
        for extension_id, extension_data in safari_extensions.items():
            extension_info = {}
            
            # Keep the original extension ID
            extension_info['extension_id'] = extension_id
            
            # Extract name from the key (e.g., com.example.extension -> Example)
            clean_id = extension_id.split(' ')[0].split('(')[0]
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
            if 'WebsiteAccess' in extension_data:
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
        if "stream had too few bytes" not in str(e):
            print(f"Error processing Safari extensions: {str(e)}")
    
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
                        
                        # Create a unique key for this extension
                        unique_key = f"{extension_data['user']}|{extension_data['browser']}|{extension_data['profile']}|{extension_data['extension_id']}"
                        
                        # Only add if we haven't seen this extension before, or if it's newer
                        if unique_key not in unique_extensions or int(float(extension_data['date_installed'])) > int(float(unique_extensions[unique_key]['date_installed'])):
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
                        
                        # Create a unique key for this extension
                        unique_key = f"{extension_data['user']}|{extension_data['browser']}|{extension_data['profile']}|{extension_data['extension_id']}"
                        
                        # Only add if we haven't seen this extension before, or if it's newer
                        if unique_key not in unique_extensions or int(float(extension_data['date_installed'])) > int(float(unique_extensions[unique_key]['date_installed'])):
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
                    if unique_key not in unique_extensions or int(float(extension_data['date_installed'])) > int(float(unique_extensions[unique_key]['date_installed'])):
                        unique_extensions[unique_key] = extension_data

        # Check for Safari extensions - using the original approach
        safari_extension_paths = [
            user+"/Library/Containers/com.apple.Safari/Data/Library/Safari/AppExtensions/Extensions.plist",
            user+"/Library/Containers/com.apple.Safari/Data/Library/Safari/WebExtensions/Extensions.plist"
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
                        if unique_key not in unique_extensions or int(float(extension['date_installed'])) > int(float(unique_extensions[unique_key]['date_installed'])):
                            unique_extensions[unique_key] = extension
                except Exception as e:
                    # Log all errors
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
