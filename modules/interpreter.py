import re
import click
from requests.api import head
from tqdm import tqdm
from contextlib import suppress
from dataclasses import replace
from pathlib import Path
from posixpath import dirname, split
from sys import exit
from urllib.parse import urlparse
from modules.helpers import *
from modules.postfix import Conversion, Evaluate
from sys import exit
import hcl2

# # Inject parent module variables that are referenced downstream in sub modules
# if tfdata.get("all_module"):
#     tfdata["variable_map"] = inject_module_variables(
#         tfdata["all_module"], tfdata["variable_map"]
#     )
# if tfdata.get("all_locals"):
#     # Evaluate Local Variables containing functions and TF variables and replace with evaluated values
#     tfdata["all_locals"] = extract_locals(
#         tfdata["all_locals"], variable_list, tfdata.get("all_output")
#     )
# # Get metadata from resource attributes
# data = get_metadata(
#     tfdata["all_resource"],
#     tfdata.get("variable_map"),
#     tfdata.get("all_locals"),
#     tfdata.get("all_output"),
#     tfdata.get("all_module"),
#     module_source_dict,
# )
# tfdata["meta_data"] = data["meta_data"]
# tfdata["node_list"] = data["node_list"]
# tfdata["hidden"] = data["hide"]
# tfdata["annotations"] = annotations
# # Dump out findings after file scans are complete
# output_log(tfdata, variable_list)
# # Check for annotations
# temp_dir.cleanup()
# os.chdir(cwd)5eszesz
# return tfdata


def inject_module_variables(tfdata: dict):
    for file, module_list in tfdata["all_module"].items():
        for module_items in module_list:
            for module, params in module_items.items():
                module_source = params["source"]
                for key, value in params.items():
                    if "var." in str(value):
                        if isinstance(value, list):
                            for i in range(len(value)):
                                value[i] = replace_variables(
                                    value[i],
                                    module_source,
                                    tfdata["variable_map"]["main"],
                                    False,
                                )
                        else:
                            value = replace_variables(
                                value,
                                module_source,
                                tfdata["variable_map"]["main"],
                                False,
                            )
                    # Add var value to master list of all variables so it can be used downstream
                    if (
                        key != "source" and key != "version"
                    ):  # and key in all_variables.keys():
                        tfdata["variable_map"][module][key] = value
    # Add quotes for raw strings to aid postfix evaluation
    for module in tfdata["variable_map"]:
        for variable in tfdata["variable_map"][module]:
            value = tfdata["variable_map"][module][variable]
            if (
                isinstance(value, str)
                and "(" not in value
                and "[" not in value
                and not value.startswith('"')
            ):
                tfdata["variable_map"][module][variable] = f'"{value}"'
    return tfdata

def handle_metadata_vars(tfdata) :
    for resource, attr_list in tfdata['meta_data'].items():
        for key, value in attr_list.items():
            if "var." in value or "local." in value or "module." in value or "data." in value :
                find_replace_values(value, tfdata)
    return tfdata


def find_replace_values(value, tfdata) :
    oldvalue = value
    self_reference = False
    if self_reference:
        return value
    var_found_list = re.findall("var\.[A-Za-z0-9_\-]+", value)
    data_found_list = re.findall("data\.[A-Za-z0-9_\-\.\[\]]+", value)
    varobject_found_list = re.findall(
        "var\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+", value
    )
    local_found_list = re.findall("local\.[A-Za-z0-9_\-]+", value)
    modulevar_found_list = re.findall(
        "module\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+", value
    )
    for d in data_found_list:
        value = value.replace(d, '"UNKNOWN"')
    for module in modulevar_found_list:
        cleantext = fix_lists(module)
        splitlist = cleantext.split(".")
        outputname = find_between(cleantext, splitlist[1] + ".", " ")
        oldvalue = value
        for ofile in tfdata['all_output'].keys():
            for i in tfdata['all_output'][ofile]:
                if outputname in i.keys():
                    value = value.replace(module, i[outputname]["value"])
                    break
        if value == oldvalue:
            value = value.replace(module, "UNKNOWN")
    for varitem in var_found_list:
        lookup = varitem.split("var.")[1].lower()
        if lookup in tfdata['variable_map'].keys() and "var." + lookup not in str(tfdata['variable_map'][lookup]):
            # Possible object type var encountered
            obj = ""
            for item in varobject_found_list:
                if lookup in item:
                    obj = tfdata['variable_map'][lookup]
                    varitem = item
            # click.echo(f'    var.{lookup}')
            if value.count(lookup) < 2 and obj != "" and isinstance(obj, dict):
                key = varitem.split(".")[2]
                keyvalue = obj[key]
                if (
                    isinstance(keyvalue, str)
                    and not keyvalue.startswith("[")
                    and not keyvalue.startswith("{")
                ):
                    keyvalue = f'"{keyvalue}"'
                value = value.replace(varitem, str(keyvalue))
            elif value.count(lookup) < 2 and obj == "":
                replacement_value = str(tfdata['variable_map'].get(lookup))
                if (
                    isinstance(replacement_value, str)
                    and '"' not in replacement_value
                    and not replacement_value.startswith("[")
                ):
                    replacement_value = f'"{replacement_value}"'
                value = value.replace(varitem, replacement_value)
            else:
                value = value.replace(varitem + " ", str(tfdata['variable_map'][lookup]) + " ")
                value = value.replace(varitem + ",", str(tfdata['variable_map'][lookup]) + ",")
                value = value.replace(varitem + ")", str(tfdata['variable_map'][lookup]) + ")")
                value = value.replace(varitem + "]", str(tfdata['variable_map'][lookup]) + "]")
        elif tfdata['variable_map']['main'].get(lookup):
            # Self referencing variable (duplicate across modules)
            value = value.replace(varitem, str(tfdata['variable_map']['main'].get(lookup)))
            self_reference = True
            break
        else:
            click.echo(
                click.style(
                    f"\nERROR: No variable value supplied for {varitem} but it is referenced in {value} ",
                    fg="white",
                    bold=True,
                )
            )
            click.echo(
                "Consider passing a valid Terraform .tfvars variable file with the --varfile parameter\n"
            )
            exit()
    for localitem in local_found_list:
        lookup = localitem.split("local.")[1]
        if tfdata['all_locals']:
            if lookup in tfdata['all_locals'].keys():
                replacement_value = tfdata['all_locals'].get(lookup)
                value = value.replace(localitem, replacement_value)
            else:
                value = value.replace(localitem, "None")
                click.echo(
                    f"    WARNING: Cannot resolve {localitem}, assigning empty value"
                )
        else:
            value = value.replace(localitem, "None")
            click.echo(
                f"    WARNING: Cannot resolve {localitem}, assigning empty value"
            )
    if oldvalue == value:
        click.echo(f"    WARNING: Cannot resolve {lookup}")
        return value
    return value


# def handle_metadata_vars(tfdata):
# # Determine which module's variables we should use
# for resource, attr_list in tfdata['meta_data'].items():
# for value in attr_list:
# self_reference = False
# while (
#     "var." in value or "local." in value or "module." in value or "data." in value
# ):
                


def extract_locals(tfdata):
    click.echo("\n  Parsing locals...")
    final_locals = dict()
    module_locals = dict()
    # Remove array layer of locals dict structure and copy over to final_locals dict first
    for file, localvarlist in tfdata["all_locals"].items():
        final_locals[file] = localvarlist[0]
        if ";" in file:
            modname = file.split(";")[1]
        else:
            modname = "main"
        if module_locals.get(modname):
            module_locals[modname] = {**module_locals[modname], **localvarlist[0]}
        else:
            module_locals[modname] = localvarlist[0]
    tfdata["all_locals"] = module_locals
    return tfdata


# def process_conditional_metadata(
#     metadata: dict, mod_locals, all_variables, all_outputs, filename, mod
# ):
#     def determine_statement(eval_string: str):
#         if "for" in eval_string and "in" in eval_string:
#             # we have a for loop so deal with that part first
#             # TODO: Implement for loop handling for real, for now just null it out
#             eval_string = find_between(
#                 eval_string, "[for", ":", "[", True, eval_string.count("[")
#             )
#             eval_string = find_between(
#                 eval_string, ":", "]", "", True, eval_string.count("]")
#             )
#         if "module." in eval_string:
#             outvalue = ""
#             splitlist = eval_string.split(".")
#             outputname = find_between(eval_string, splitlist[1] + ".", " ")
#             for file in all_outputs.keys():
#                 for i in all_outputs[file]:
#                     if outputname in i.keys():
#                         outvalue = i[outputname]["value"]
#                         if "*.id" in outvalue:
#                             resource_name = fix_lists(outvalue.split(".*")[0])
#                             outvalue = metadata[resource_name]["count"]
#                             outvalue = determine_statement(outvalue)
#                             break
#             stringarray = eval_string.split(".")
#             modulevar = cleanup(
#                 "module" + "." + stringarray[1] + "." + stringarray[2]
#             ).strip()
#             eval_string = eval_string.replace(modulevar, outvalue)
#         eval_string = resolve_dynamic_values(
#             eval_string, mod_locals, all_variables, all_outputs, filename
#         )
#         return eval_string

#         if "for_each" in attr_list:
#             attr_list["for_each"] = determine_statement(attr_list["for_each"])
#     return metadata



# def determine_statement(eval_string: str, tfdata: dict):
#     # Handle for loops
#     if "for" in eval_string and "in" in eval_string:
#         # we have a for loop so deal with that part first
#         # TODO: Implement for loop handling for real, for now just null it out
#         eval_string = find_between(
#             eval_string, "[for", ":", "[", True, eval_string.count("[")
#         )
#         eval_string = find_between(
#             eval_string, ":", "]", "", True, eval_string.count("]")
#         )
#     # Handle cases where value of module variable is referenced
#     if "module." in eval_string:
#         outvalue = ""
#         splitlist = eval_string.split(".")
#         outputname = find_between(eval_string, splitlist[1] + ".", " ")
#         for file in tfdata[''].keys():
#             for i in tfdata.get("all_output")[file]:
#                 if outputname in i.keys():
#                     outvalue = i[outputname]["value"]
#                     if "*.id" in outvalue:
#                         resource_name = fix_lists(outvalue.split(".*")[0])
#                         outvalue = tfdata['meta_data'][resource_name]["count"]
#                         outvalue = determine_statement(outvalue)
#                         break
#         stringarray = eval_string.split(".")
#         modulevar = cleanup(
#             "module" + "." + stringarray[1] + "." + stringarray[2]
#         ).strip()
#         eval_string = eval_string.replace(modulevar, outvalue)
#     # Otherwise just replace vars with actual values
#     eval_string = resolve_dynamic_values(
#         eval_string, mod_locals, all_variables, all_outputs, filename
#     )
#     return eval_string

# def handle_metadata_vars(tfdata) :
#     for resource, attr_list in tfdata['meta_data'].items():
#         if (
#             "count" in attr_list.keys()
#             and not isinstance(attr_list["count"], int)
#             and not resource.startswith("null_resource")
#         ):
#             eval_string = str(attr_list["count"])
#             eval_string = determine_statement(eval_string, tfdata)
#             exp = handle_conditionals(eval_string, mod_locals, all_variables, filename)
#             filepath = Path(filename)
#             fname = filepath.parent.name + "/" + filepath.name
#             # fname = filename.split('_')[-2] + filename.split('_')[-1]
#             if not "ERROR!" in exp:
#                 obj = Conversion(len(exp))
#                 pf = obj.infixToPostfix(exp)
#                 if not pf == "ERROR!":
#                     obj = Evaluate(len(pf))
#                     eval_value = obj.evaluatePostfix(pf)
#                     if eval_value == "" or eval_value == " ":
#                         eval_value = 0
#                     fname2 = fname.replace(";", "|")
#                     click.echo(
#                         f"    {fname2} : {resource} count = {eval_value} ({exp})"
#                     )
#                     attr_list["count"] = int(eval_value)
#                 else:
#                     click.echo(
#                         f"    ERROR: {fname} : {resource} count = 0 (Error in evaluation of value {exp})"
#                     )
#             else:
#                 click.echo(
#                     f"    ERROR: {fname} : {resource} count = 0 (Error in calling function {exp}))"
#                 )
#     return tfdata



def get_metadata(tfdata) : #  -> set
    """
    Extract resource attributes from resources by looping through each resource in each file.
    Returns a set with a node_list of unique resources, resource attributes (metadata) and hidden (zero count) nodes
    """
    node_list = []
    meta_data = dict()
    variable_list = tfdata.get("variable_map")
    all_locals = tfdata.get("all_locals")
    all_outputs = tfdata.get("all_output")
    click.echo(f"\n  Conditional Resource List:")
    for filename, resource_list in tfdata["all_resource"].items():
        if ";" in filename:
            # We have a module file being processed
            modarr = filename.split(";")
            mod = modarr[1]
        else:
            mod = "main"
        for item in resource_list:
            for k in item.keys():
                resource_type = k
                for i in item[k]:
                    resource_name = i
                    # Check if Cloudwatch is present in policies and create node for Cloudwatch service if found
                    if resource_type == "aws_iam_policy":
                        if "logs:" in item[resource_type][resource_name]["policy"][0]:
                            if not "aws_cloudwatch_log_group.logs" in node_list:
                                node_list.append("aws_cloudwatch_log_group.logs")
                            meta_data["aws_cloudwatch_log_group.logs"] = item[
                                resource_type
                            ][resource_name]
                # click.echo(f'    {resource_type}.{resource_name}')
                node_list.append(f"{resource_type}.{resource_name}")
                # Check if any variables are present and replace with values if known
                attribute_values = item[k][i]
                for attribute, attribute_value in attribute_values.items():
                    if isinstance(attribute_value, list):
                        for index, listitem in enumerate(attribute_value):
                            if "var." in str(listitem):
                                attribute_value[index] = replace_variables(
                                    listitem, filename, variable_list[mod]
                                )
                            if "local." in str(listitem):
                                attribute_value[index] = replace_locals(
                                    str(listitem), all_locals[mod]
                                )
                    if isinstance(attribute_value, str):
                        if "var." in attribute_value:
                            attribute_values[attribute] = replace_variables(
                                attribute_value, filename, variable_list[mod]
                            )
                        if "local." in attribute_value:
                            attribute_values[attribute] = replace_locals(
                                attribute_value, all_locals[mod]
                            )
                meta_data[f"{resource_type}.{resource_name}"] = attribute_values
        # meta_data = process_conditional_metadata(
        #     meta_data,
        #     all_locals.get(mod) if all_locals else None,
        #     variable_list.get(mod) if variable_list else None,
        #     all_outputs,
        #     filename,
        #     mod,
        # )

    # Handle CF Special meta data
    cf_data = [s for s in meta_data.keys() if "aws_cloudfront" in s]
    if cf_data:
        for cf_resource in cf_data:
            if "origin" in meta_data[cf_resource]:
                for origin_source in meta_data[cf_resource]["origin"]:
                    if isinstance(origin_source, str) and origin_source.startswith("{"):
                        origin_source = literal_eval(origin_source)
                    origin_domain = cleanup(origin_source.get("domain_name")).strip()
                    if origin_domain:
                        meta_data[cf_resource]["origin"] = handle_cloudfront_domains(
                            str(origin_source), origin_domain, meta_data
                        )
    to_hide = [
        key
        for key, attr_list in meta_data.items()
        if str(attr_list.get("count")) == "0"
    ]
    tfdata['meta_data'] = meta_data
    tfdata['node_list'] = node_list
    tfdata['to_hide'] = to_hide
    return tfdata


def handle_cloudfront_domains(origin_string: str, domain: str, mdata: dict) -> str:
    for key, value in mdata.items():
        for k, v in value.items():
            if domain in str(v) and not domain.startswith("aws_"):
                o = origin_string.replace(domain, key)
                return origin_string.replace(domain, key)
    return origin_string


def get_variable_values(tfdata) -> dict:
    """Returns a list of all variables from local .tfvar defaults, supplied varfiles and module var values"""
    click.echo("Processing Variables..")
    if not tfdata.get("all_variable"):
        tfdata["all_variable"] = dict()
    var_data = dict()
    var_mappings = dict()
    # Load default values from all existing files in source locations
    for var_source_file, var_list in tfdata["all_variable"].items():
        var_source_dir = str(Path(var_source_file).parent)
        for item in var_list:
            for k in item.keys():
                var_name = k
                for var_attr in item[k]:
                    # Populate dict with default values first
                    if (
                        var_attr == "default"
                    ):  # and not var_name in variable_values.keys():
                        if item[k][var_attr] == "":
                            var_value = ""
                        else:
                            var_value = item[k][var_attr]
                        var_data[var_name] = var_value
                        # Also update var mapping dict with modules and matching variables
                        matching = [
                            m
                            for m in tfdata["module_source_dict"]
                            if tfdata["module_source_dict"][m]["cache_path"][1:-1]
                            in str(var_source_file)
                        ]  # omit first char of module source in case it is a .
                        if not matching:
                            if not var_mappings.get("main"):
                                var_mappings["main"] = {}
                                var_mappings["main"] = {"source_dir": var_source_dir}
                            var_mappings["main"][var_name] = var_value
                        for mod in matching:
                            if not var_mappings.get(mod):
                                var_mappings[mod] = {}
                                var_mappings[mod]["source_dir"] = var_source_dir
                            var_mappings[mod][var_name] = var_value
    if tfdata["module_source_dict"]:
        # Insert module parameters as variable names
        for file, modulelist in tfdata["all_module"].items():
            for module in modulelist:
                for mod, params in module.items():
                    for variable in params:
                        var_data[variable] = params[variable]
                        if not var_mappings.get(mod):
                            var_mappings[mod] = {}
                        var_mappings[mod][variable] = params[variable]
    if tfdata.get("all_variable"):
        # Over-write defaults with passed varfile specified values
        for varfile in tfdata.get("all_variable"):
            # Open supplied varfile for reading
            with click.open_file(varfile, "r") as f:
                variable_values = hcl2.load(f)
            for uservar in variable_values:
                var_data[uservar.lower()] = variable_values[uservar]
                if not var_mappings.get("main"):
                    var_mappings["main"] = {}
                var_mappings["main"]  = var_mappings["main"] | variable_values['variable']
    #tfdata["variable_list"] = var_data
    tfdata["variable_map"] = var_mappings
    return tfdata