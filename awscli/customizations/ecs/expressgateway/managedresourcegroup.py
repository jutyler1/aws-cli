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

diff --git a/awscli/customizations/ecs/expressgateway/managedresourcegroup.py b/awscli/customizations/ecs/expressgateway/managedresourcegroup.py
index b5643bc3b..959cdf745 100644
--- a/awscli/customizations/ecs/expressgateway/managedresourcegroup.py
+++ b/awscli/customizations/ecs/expressgateway/managedresourcegroup.py
@@ -39,7 +39,7 @@ class ManagedResourceGroup:
     ):
         self.resource_type = resource_type
         self.identifier = identifier
-        # maintain input ordering
+        # Maintain input ordering
         self.sorted_resource_keys = [
             self._create_key(resource) for resource in resources
         ]
@@ -57,6 +57,90 @@ class ManagedResourceGroup:
         identifier = resource.identifier if resource.identifier else ""
         return resource_type + "/" + identifier
 
+    def get_stream_string(self, timestamp, use_color=True):
+        """Returns flattened stream strings for all resources in the group.
+
+        Args:
+            timestamp (str): Timestamp string to prefix each resource
+            use_color (bool): Whether to use ANSI color codes (default: True)
+
+        Returns:
+            str: All flattened resources formatted for stream display, separated by newlines
+        """
+        from awscli.customizations.ecs.expressgateway.managedresource import (
+            ManagedResource,
+        )
+
+        flat_resources = []
+
+        for resource in self.resource_mapping.values():
+            if isinstance(resource, ManagedResourceGroup):
+                # Recursively flatten nested groups
+                nested = resource.get_stream_string(timestamp, use_color)
+                if nested:
+                    flat_resources.append(nested)
+            elif isinstance(resource, ManagedResource):
+                # Get stream string for individual resource
+                flat_resources.append(
+                    resource.get_stream_string(timestamp, use_color)
+                )
+
+        return "\n".join(flat_resources)
+
+    def get_changed_resources(self, previous_resources_dict):
+        """Get flattened list of resources that have changed properties.
+
+        Compares individual resource properties (status, reason, updated_at, etc.)
+        against previous state to detect changes. This is used for change detection
+        in TEXT-ONLY mode, NOT for DEPLOYMENT diff (use compare_resource_sets for that).
+
+        Args:
+            previous_resources_dict: Dict of {(resource_type, identifier): ManagedResource}
+                from previous poll. Can be empty dict for first poll.
+
+        Returns:
+            tuple: (changed_resources, updated_dict, removed_keys)
+                - changed_resources: List of ManagedResource that changed or None if no changes
+                - updated_dict: Updated dict with current resources for next comparison
+                - removed_keys: Set of keys that were removed since last poll
+        """
+        current_resources = self._flatten_to_list()
+        changed_resources = []
+        updated_dict = {}
+
+        for resource in current_resources:
+            resource_key = (resource.resource_type, resource.identifier)
+            previous_resource = previous_resources_dict.get(resource_key)
+
+            if not previous_resource:
+                changed_resources.append(resource)
+            else:
+                if resource.compare_properties(previous_resource):
+                    changed_resources.append(resource)
+
+            updated_dict[resource_key] = resource
+
+        current_keys = {
+            (r.resource_type, r.identifier) for r in current_resources
+        }
+        removed_keys = set(previous_resources_dict.keys()) - current_keys
+
+        return (
+            changed_resources if changed_resources else None,
+            updated_dict,
+            removed_keys,
+        )
+
+    def _flatten_to_list(self):
+        """Flatten this resource group into a list of individual resources."""
+        flat_list = []
+        for resource in self.resource_mapping.values():
+            if isinstance(resource, ManagedResourceGroup):
+                flat_list.extend(resource._flatten_to_list())
+            elif isinstance(resource, ManagedResource):
+                flat_list.append(resource)
+        return flat_list
+
     def is_terminal(self):
         return not self.resource_mapping or all(
             [
@@ -188,8 +272,12 @@ class ManagedResourceGroup:
         else:
             return resource_b
 
-    def diff(self, other_resource_group):
-        """Returns two ManagedResourceGroups representing unique resources in each group.
+    def compare_resource_sets(self, other_resource_group):
+        """Compares resource SETS between two groups to find additions/removals.
+
+        This is used for DEPLOYMENT view to show which resources were added or removed
+        between service configurations, NOT for detecting property changes within
+        individual resources (that's compare_properties() in ManagedResource).
 
         Args:
             other_resource_group (ManagedResourceGroup): Resource group to compare against
@@ -218,7 +306,7 @@ class ManagedResourceGroup:
         common_keys = self_keys & other_keys
 
         common_diff = {
-            key: self.resource_mapping[key].diff(
+            key: self.resource_mapping[key].compare_resource_sets(
                 other_resource_group.resource_mapping.get(key)
             )
             for key in common_keys
