#!/usr/local/munkireport/munkireport-python3

import os
import subprocess
import sys
import re
import glob
import json

sys.path.insert(0, '/usr/local/munki')
sys.path.insert(0, '/usr/local/munkireport')

from munkilib import FoundationPlist

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
            users.append(user.replace("NFSHomeDirectory: ", ""))

    return users

def process_chrome(chrome_extension, user, browser, profile=None):

    extension_manifest = json.loads(open(chrome_extension, 'r').read().strip())
    
    extension_info = {}

    for item in extension_manifest:
        if item == "version":
            extension_info['version'] = extension_manifest[item]

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
                extension_info['name'] = extension_localization_lower[local_name]["message"]
            except:
                extension_info['description'] = ""
        elif item == "name":
            extension_info['name'] = extension_manifest[item]

    path_dict = chrome_extension.split('/')
    extension_info['extension_id'] = path_dict[-3:][0]
    extension_info['user'] = user
    extension_info['date_installed'] = str(int(os.path.getmtime(chrome_extension)))
    extension_info['browser'] = browser
    
    # Store profile in its own field
    if profile:
        extension_info['profile'] = profile
    
    # Store extension path
    extension_info['extension_path'] = chrome_extension.replace("manifest.json","")
        
    return extension_info

def process_firefox(firefox_extension, user, firefox_extension_path, profile=None):

    extension_info = {}
    
    # Store extension path
    extension_info['extension_path'] = firefox_extension_path

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
            
        elif item == "defaultLocale":
            
            for locale_item in firefox_extension[item]:
                if locale_item == "description" and firefox_extension[item][locale_item]:
                    extension_info['description'] = firefox_extension[item][locale_item]
                elif locale_item == "name" and firefox_extension[item][locale_item]:
                    extension_info['name'] = firefox_extension[item][locale_item]
                elif locale_item == "creator" and firefox_extension[item][locale_item]:
                    extension_info['developer'] = firefox_extension[item][locale_item]

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
            
            # Extract name from the bundle identifier (com.example.extension -> extension)
            # Try to get a more user-friendly name
            clean_id = extension_id.split(' (')[0] if ' (' in extension_id else extension_id
            name_parts = clean_id.split('.')
            if len(name_parts) > 1:
                # Get the last meaningful part of the bundle ID
                extension_info['name'] = name_parts[-2].capitalize()
            else:
                extension_info['name'] = clean_id
                
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
                        if unique_key not in unique_extensions or int(extension_data['date_installed']) > int(unique_extensions[unique_key]['date_installed']):
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
                        if unique_key not in unique_extensions or int(extension_data['date_installed']) > int(unique_extensions[unique_key]['date_installed']):
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
                    if unique_key not in unique_extensions or int(extension_data['date_installed']) > int(unique_extensions[unique_key]['date_installed']):
                        unique_extensions[unique_key] = extension_data

        # Check for Safari extensions - using the original approach
        safari_extension_path = user+"/Library/Containers/com.apple.Safari/Data/Library/Safari/AppExtensions/Extensions.plist"
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
                    if unique_key not in unique_extensions or int(extension['date_installed']) > int(unique_extensions[unique_key]['date_installed']):
                        unique_extensions[unique_key] = extension
            except Exception as e:
                # Only log serious errors, not just empty files
                if "stream had too few bytes" not in str(e):
                    print(f"Error processing Safari extensions for {user}: {str(e)}")

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
