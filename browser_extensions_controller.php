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
        // Sanitize input - fix regex pattern
        $column = preg_replace("/[^A-Za-z0-9_\-]+/", '', $column);
        
        // Whitelist allowed columns to prevent column injection
        $allowed_columns = [
            'extension_id', 'name', 'version', 'browser', 'profile', 'date_installed',
            'description', 'developer', 'enabled', 'user', 'extension_path'
        ];
        
        if (empty($column) || !in_array($column, $allowed_columns)) {
            jsonView([]);
            return;
        }

        $query = Browser_extensions_model::selectRaw("COUNT(*) AS count, `$column`")
            ->whereNotNull($column)
            ->where($column, '<>', '')
            ->groupBy($column)
            ->orderBy('count', 'desc')
            ->filter()
            ->get()
            ->toArray();

        jsonView($query);
    }
} // End class Browser_extensions_controller