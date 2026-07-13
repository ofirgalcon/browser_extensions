<?php

use CFPropertyList\CFPropertyList;
use munkireport\processors\Processor;

class Browser_extensions_processor extends Processor
{

    /**
     * Process data sent by postflight
     *
     * @param string data
     * @author abn290
     **/
    public function run($plist)
    {    
        // Add local config
        configAppendFile(__DIR__ . '/config.php');

        // Check if we have data
		if ( ! $plist){
			throw new Exception("Error Processing Request: No property list found", 1);
		}

        // Delete previous set
        Browser_extensions_model::where('serial_number', $this->serial_number)->delete();

        // Build list of extension IDs to ignore (exact match)
        $extension_id_ignorelist = is_array(conf('browser_extension_id_ignorelist')) ? conf('browser_extension_id_ignorelist') : array();
        $extension_id_ignorelist = array_values(array_filter($extension_id_ignorelist, function ($item) {
            return is_string($item) && $item !== '';
        }));

        // Build list of extension names to ignore (case-insensitive exact match)
        $extension_name_ignorelist = is_array(conf('browser_extension_name_ignorelist')) ? conf('browser_extension_name_ignorelist') : array();
        $extension_name_ignorelist = array_values(array_filter($extension_name_ignorelist, function ($item) {
            return is_string($item) && $item !== '';
        }));
        $extension_name_ignoremap = array_flip(array_map('strtolower', $extension_name_ignorelist));

		$parser = new CFPropertyList();
        $parser->parse($plist, CFPropertyList::FORMAT_XML);

        // Get fillable items
        $fillable = array_fill_keys((new Browser_extensions_model)->getFillable(), null);
        $fillable['serial_number'] = $this->serial_number;

        $save_list = [];
        foreach ($parser->toArray() as $extension) {

            $extension_id = isset($extension['extension_id']) ? $extension['extension_id'] : '';
            if ($extension_id !== '' && in_array($extension_id, $extension_id_ignorelist, true)) {
                continue;
            }     

            $extension_name = isset($extension['name']) ? $extension['name'] : '';
            if ($extension_name !== '' && isset($extension_name_ignoremap[strtolower($extension_name)])) {
                continue;
            }

            $save_list[] = array_replace($fillable, array_intersect_key($extension, $fillable));
        }

        Browser_extensions_model::insertChunked($save_list);
    }
}