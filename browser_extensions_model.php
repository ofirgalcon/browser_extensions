<?php

use munkireport\models\MRModel as Eloquent;

class Browser_extensions_model extends Eloquent
{
    protected $table = 'browser_extensions';

    protected $fillable = [
		'serial_number',
		'name',
		'extension_id',
		'version',
		'description',
		'browser',
		'profile',
		'date_installed',
		'developer',
		'enabled',
		'user',
		'extension_path',
    ];

    public $timestamps = false;
    
    /**
     * Execute a raw query
     *
     * @param string $sql SQL query
     * @return array result
     */
    public function rawQuery($sql)
    {
        return $this->getConnection()->select($sql);
    }
}
