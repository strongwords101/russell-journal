# reminder.ps1 — Russell Journal nudge notification
# Called by Task Scheduler (random delay is set in the task itself, not here)

$url = "http://localhost:5055"

try {
    # Load Windows Runtime toast APIs
    [Windows.UI.Notifications.ToastNotificationManager,
     Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    [Windows.Data.Xml.Dom.XmlDocument,
     Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null

    $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
    $xml.LoadXml(@"
<toast activationType="protocol" launch="$url" duration="long">
  <visual>
    <binding template="ToastGeneric">
      <text>Russell Journal</text>
      <text>What are the facts? Two minutes, then back to your day.</text>
    </binding>
  </visual>
  <actions>
    <action content="Open journal" activationType="protocol" arguments="$url"/>
    <action content="Later"        activationType="system"   arguments="dismiss"/>
  </actions>
</toast>
"@)

    $toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Russell Journal").Show($toast)

} catch {
    # Fallback: just open the browser directly
    Start-Process $url
}
