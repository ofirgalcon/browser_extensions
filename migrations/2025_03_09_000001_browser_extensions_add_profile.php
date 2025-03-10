<?php
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Capsule\Manager as Capsule;

class BrowserExtensionsAddProfile extends Migration
{
    private $tableName = 'browser_extensions';

    public function up()
    {
        $capsule = new Capsule();
        
        $capsule::schema()->table($this->tableName, function (Blueprint $table) {
            $table->string('profile')->nullable()->after('browser');
            $table->index('profile');
        });
    }

    public function down()
    {
        $capsule = new Capsule();
        
        $capsule::schema()->table($this->tableName, function (Blueprint $table) {
            $table->dropColumn('profile');
        });
    }
} 