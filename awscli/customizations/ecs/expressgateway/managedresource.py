commit 1fabd632712c051629cc0bf6379603717d491850
Author: Tyler Jung <jutyler@amazon.com>
Date:   Tue Dec 9 20:54:03 2025 -0500

    refactor(ecs): integrate display modes and extract validation logic
    
    Integrate text-only display infrastructure with existing monitoring commands
    and extract validation logic for better code organization:
    
    Command integration:
    - monitorexpressgatewayservice.py: Add --mode parameter, integrate display strategies
    - monitormutatinggatewayservice.py: Add --monitor-mode parameter, TTY validation
    - Change mode names to lowercase (interactive, text-only)
      Aligns with AWS CLI conventions (e.g., --color on/off/auto)
    
    Validation methods (testable via public interface):
    - _parse_monitor_resources(): Parse monitor-resources value
    - _validate_and_parse_mode(): Validate mode with error handling
    - _determine_display_mode(): Auto-detect or validate display mode
    - _parse_and_validate_monitoring_args(): Orchestrate validation
    
    TTY handling:
    - Interactive mode requires TTY (validated with clear error)
    - Text-only mode works without TTY
    - Auto-detection: defaults to interactive if TTY, else text-only
    
    Error messages:
    - Clear error when --monitor-mode used without --monitor-resources
    - Actionable guidance for TTY requirements
    - Distinguish between timeout and user exit
    
    Helper updates:
    - managedresource.py: Add combine() method for resource merging
    - managedresourcegroup.py: Add diff detection, combine logic
    
    Benefits:
    - Single responsibility principle (one method, one task)
    - Better error messages with actionable guidance
    - CI/CD compatibility
    - Easier maintenance

diff --git a/awscli/customizations/ecs/expressgateway/managedresource.py b/awscli/customizations/ecs/expressgateway/managedresource.py
index f4b3303bf..23581c92a 100644
--- a/awscli/customizations/ecs/expressgateway/managedresource.py
+++ b/awscli/customizations/ecs/expressgateway/managedresource.py
@@ -113,6 +113,52 @@ class ManagedResource:
         lines.append("")
         return '\n'.join(lines)
 
+    def get_stream_string(self, timestamp, use_color=True):
+        """Returns the resource information formatted for stream/text-only display.
+
+        Args:
+            timestamp (str): Timestamp string to prefix the output
+            use_color (bool): Whether to use ANSI color codes (default: True)
+
+        Returns:
+            str: Formatted string with timestamp prefix and bracket-enclosed status
+        """
+        lines = []
+        parts = [f"[{timestamp}]"]
+
+        if self.resource_type:
+            parts.append(
+                self.color_utils.make_cyan(self.resource_type, use_color)
+            )
+
+        if self.identifier:
+            colored_id = self.color_utils.color_by_status(
+                self.identifier, self.status, use_color
+            )
+            parts.append(colored_id)
+
+        if self.status:
+            status_text = self.color_utils.color_by_status(
+                self.status, self.status, use_color
+            )
+            parts.append(f"[{status_text}]")
+
+        lines.append(" ".join(parts))
+
+        if self.reason:
+            lines.append(f"  Reason: {self.reason}")
+
+        if self.updated_at:
+            updated_time = datetime.fromtimestamp(self.updated_at).strftime(
+                "%Y-%m-%d %H:%M:%S"
+            )
+            lines.append(f"  Last Updated At: {updated_time}")
+
+        if self.additional_info:
+            lines.append(f"  Info: {self.additional_info}")
+
+        return "\n".join(lines)
+
     def combine(self, other_resource):
         """Returns the version of the resource which has the most up to date timestamp.
 
@@ -130,22 +176,28 @@ class ManagedResource:
             else other_resource
         )
 
-    def diff(self, other_resource):
-        """Returns a tuple of (self_diff, other_diff) for resources that are different.
+    def compare_properties(self, other_resource):
+        """Compares individual resource properties to detect changes.
+
+        This compares properties like status, reason, updated_at, additional_info
+        to detect if a resource has changed between polls.
 
         Args:
             other_resource (ManagedResource): Resource to compare against
 
         Returns:
-            tuple: (self_diff, other_diff) where:
-                - self_diff (ManagedResource): This resource if different, None if same
-                - other_diff (ManagedResource): Other resource if different, None if same
+            bool: True if properties differ, False if same
         """
         if not other_resource:
-            return (self, None)
-        if (
+            # No previous resource means it's new/different
+            return True
+
+        # Resources are different if any field differs
+        return (
             self.resource_type != other_resource.resource_type
             or self.identifier != other_resource.identifier
-        ):
-            return (self, other_resource)
-        return (None, None)
+            or self.status != other_resource.status
+            or self.reason != other_resource.reason
+            or self.updated_at != other_resource.updated_at
+            or self.additional_info != other_resource.additional_info
+        )
