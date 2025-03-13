<?php 

/**
 * browser_extensions module class
 *
 * @package munkireport
 * @author tuxudo
 **/
class Browser_extensions_controller extends Module_controller
{

	/*** Protect methods with auth! ****/
	function __construct()
	{
		// Store module path
		$this->module_path = dirname(__FILE__);
	}

	/**
	 * Default method
	 * @author tuxudo
	 *
	 **/
	function index()
	{
		echo "You've loaded the browser_extensions module!";
	}

	/**
     * Retrieve data in json format
     *
     **/
    public function get_data($serial_number)
    {
        jsonView(
            Browser_extensions_model::selectRaw('name, version, extension_id, user, browser, profile, date_installed, developer, enabled, description, extension_path')
                ->where('browser_extensions.serial_number', $serial_number)
                ->orderBy('name', 'asc')
                ->filter()
                ->get()
                ->toArray()
        );
    }
    
    /**
     * Get data for scroll widget
     *
     * @return void
     * @author tuxudo
     **/
    public function get_scroll_widget($column)
    {
        // Remove non-column name characters
        $column = preg_replace("/[^A-Za-z0-9_\-]]/", '', $column);

        $sql = "SELECT COUNT(CASE WHEN ".$column." <> '' AND ".$column." IS NOT NULL THEN 1 END) AS count, ".$column." 
                FROM browser_extensions
                LEFT JOIN reportdata USING (serial_number)
                ".get_machine_group_filter()."
                AND ".$column." <> '' AND ".$column." IS NOT NULL 
                GROUP BY ".$column."
                ORDER BY count DESC";

        $queryobj = new Browser_extensions_model;
        jsonView($queryobj->rawQuery($sql));
    }
} // End class Browser_extensions_controller