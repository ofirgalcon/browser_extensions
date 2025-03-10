<div id="browser_extensions-tab"></div>
<div id="lister" style="font-size: large; float: right;">
    <a href="/show/listing/browser_extensions/browser_extensions" title="List">
        <i class="btn btn-default tab-btn fa fa-list"></i>
    </a>
</div>
<h2><i class="fa fa-puzzle-piece"></i> <span data-i18n="browser_extensions.browser_extensions"></span></h2>

<div id="browser_extensions-msg" data-i18n="listing.loading" class="col-lg-12 text-center"></div>

<!-- Sub-tabs for different browsers -->
<div id="browser_extensions-tab-content">
    <style>
        /* Prevent text selection cursor on tabs */
        .nav-tabs > li > a {
            cursor: pointer;
            user-select: none;
            -webkit-user-select: none;
            -moz-user-select: none;
            -ms-user-select: none;
        }
        /* Add browser icons to tabs */
        .nav-tabs > li > a > i {
            margin-right: 5px;
        }
    </style>
    <ul class="nav nav-tabs">
        <li class="active">
            <a data-toggle="tab" data-target="#chrome-subtab"><i class="fa fa-chrome"></i> Chrome</a>
        </li>
        <li>
            <a data-toggle="tab" data-target="#edge-subtab"><i class="fa fa-internet-explorer"></i> Edge</a>
        </li>
        <li>
            <a data-toggle="tab" data-target="#firefox-subtab"><i class="fa fa-firefox"></i> Firefox</a>
        </li>
        <li>
            <a data-toggle="tab" data-target="#safari-subtab"><i class="fa fa-safari"></i> Safari</a>
        </li>
    </ul>
    <div class="tab-content" style="margin-top: 24px;">
        <div id="chrome-subtab" class="tab-pane fade in active"></div>
        <div id="edge-subtab" class="tab-pane fade"></div>
        <div id="firefox-subtab" class="tab-pane fade"></div>
        <div id="safari-subtab" class="tab-pane fade"></div>
    </div>
</div>

<script>
$(document).on('appReady', function(){
	// Get the original hash when the page loads
	const originalHash = window.location.hash || '#tab_browser_extensions-tab';

	// Use a more specific selector for just our tab container
	$('#browser_extensions-tab-content .nav-tabs a').on('click', function (e) {
		e.preventDefault();
		$(this).tab('show');
		// Restore the original hash
		if (window.location.hash !== originalHash) {
			history.pushState(null, null, originalHash);
		}
	});

	$.getJSON(appUrl + '/module/browser_extensions/get_data/' + serialNumber, function(data){
		// Check if we have data
		if(!data[0]){
			$('#browser_extensions-msg').text(i18n.t('no_data'));
			$('#browser_extensions-header').removeClass('hide');

			// Update the tab browser_extensions count
			$('#browser_extensions-cnt').text("0");
		} else {
			// Hide loading message
			$('#browser_extensions-msg').text('');
			$('#browser_extensions-view').removeClass('hide');

			// Set count of extensions
			$('#browser_extensions-cnt').text(data.length);

			// Prepare separate arrays for each browser
			const chromeExtensions = [];
			const firefoxExtensions = [];
			const edgeExtensions = [];
			const safariExtensions = [];
			
			// Process each extension and add to the appropriate array
			$.each(data, function(i, d) {
				// Generate rows from data in a specific order
				var rows = '';
				
				// Define the order of fields to display
				var fieldOrder = ['browser', 'user', 'profile', 'version', 'extension_id', 'date_installed', 'description'];
				
				// Optional fields that may not be present in all extensions
				var optionalFields = ['developer', 'enabled', 'extension_path'];
				
				// Process fields in the specified order
				fieldOrder.forEach(function(prop) {
					if (d[prop] !== undefined && d[prop] !== null && d[prop] !== '' && prop !== 'name') {
						if ((prop == 'enabled') && d[prop] == 1){
							rows += '<tr><th>'+i18n.t('browser_extensions.'+prop)+'</th><td>'+i18n.t('yes')+'</td></tr>';
						} else if ((prop == 'enabled') && d[prop] == 0){
							rows += '<tr><th>'+i18n.t('browser_extensions.'+prop)+'</th><td>'+i18n.t('no')+'</td></tr>';
						} else if (prop === "date_installed" && d[prop] > 100) {
							var date = new Date(d[prop] * 1000);
							rows += '<tr><th>'+i18n.t('browser_extensions.'+prop)+'</th><td><span title="'+moment(date).fromNow()+'">'+moment(date).format('llll')+'</span></td></tr>';
						} else {
							rows += '<tr><th>'+i18n.t('browser_extensions.'+prop)+'</th><td>'+d[prop]+'</td></tr>';
						}
					}
				});
				
				// Add any remaining optional fields that weren't in the main order
				optionalFields.forEach(function(prop) {
					if (d[prop] !== undefined && d[prop] !== null && d[prop] !== '' && prop !== 'name') {
						if (prop === 'enabled' && d[prop] == 1) {
							rows += '<tr><th>'+i18n.t('browser_extensions.'+prop)+'</th><td>'+i18n.t('yes')+'</td></tr>';
						} else if (prop === 'enabled' && d[prop] == 0) {
							rows += '<tr><th>'+i18n.t('browser_extensions.'+prop)+'</th><td>'+i18n.t('no')+'</td></tr>';
						} else {
							rows += '<tr><th>'+i18n.t('browser_extensions.'+prop)+'</th><td>'+d[prop]+'</td></tr>';
						}
					}
				});

				// Create the extension HTML
				var extensionHtml = '<div class="extension-item">' +
					'<h4>';
                
                // Add the appropriate browser icon
                if (d.browser === "Google Chrome") {
                    extensionHtml += '<i class="fa fa-chrome"></i> ';
                } else if (d.browser === "Firefox") {
                    extensionHtml += '<i class="fa fa-firefox"></i> ';
                } else if (d.browser === "Microsoft Edge") {
                    extensionHtml += '<i class="fa fa-internet-explorer"></i> ';
                } else if (d.browser === "Safari") {
                    extensionHtml += '<i class="fa fa-safari"></i> ';
                }
                
                extensionHtml += d.name + '</h4>' +
					'<div style="max-width:900px;">' +
					'<table class="table table-striped table-condensed">' +
					'<tbody>' + rows + '</tbody>' +
					'</table>' +
					'</div>' +
					'</div>';

				// Add to the appropriate array based on browser
				if (d.browser === "Google Chrome") {
					chromeExtensions.push(extensionHtml);
				} else if (d.browser === "Firefox") {
					firefoxExtensions.push(extensionHtml);
				} else if (d.browser === "Microsoft Edge") {
					edgeExtensions.push(extensionHtml);
				} else if (d.browser === "Safari") {
					safariExtensions.push(extensionHtml);
				}
			});

			// Add browser counts to tab labels
			$('#browser_extensions-tab-content .nav-tabs a[data-target="#chrome-subtab"]').append(' <span class="badge">' + chromeExtensions.length + '</span>');
			$('#browser_extensions-tab-content .nav-tabs a[data-target="#edge-subtab"]').append(' <span class="badge">' + edgeExtensions.length + '</span>');
			$('#browser_extensions-tab-content .nav-tabs a[data-target="#firefox-subtab"]').append(' <span class="badge">' + firefoxExtensions.length + '</span>');
			$('#browser_extensions-tab-content .nav-tabs a[data-target="#safari-subtab"]').append(' <span class="badge">' + safariExtensions.length + '</span>');

			// Insert the extensions into their respective tabs
			$('#chrome-subtab').html(chromeExtensions.length ? chromeExtensions.join('') : '<div class="alert alert-info">No Chrome extensions found</div>');
			$('#edge-subtab').html(edgeExtensions.length ? edgeExtensions.join('') : '<div class="alert alert-info">No Edge extensions found</div>');
			$('#firefox-subtab').html(firefoxExtensions.length ? firefoxExtensions.join('') : '<div class="alert alert-info">No Firefox extensions found</div>');
			$('#safari-subtab').html(safariExtensions.length ? safariExtensions.join('') : '<div class="alert alert-info">No Safari extensions found</div>');
		}
	});
});
</script>
