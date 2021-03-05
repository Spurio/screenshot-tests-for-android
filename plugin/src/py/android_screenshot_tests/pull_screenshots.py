#!/usr/bin/env python
# Copyright (c) Facebook, Inc. and its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import codecs
import getopt
import json
import shutil
import subprocess, os, platform
import sys
import tempfile
import urllib
import xml.etree.ElementTree as ET
import zipfile
from os.path import abspath
from os.path import join

from . import aapt
from . import common
from . import metadata
from .device_name_calculator import DeviceNameCalculator
from .no_op_device_name_calculator import NoOpDeviceNameCalculator
from .simple_puller import SimplePuller

try:
    from Queue import Queue
except ImportError:
    from queue import Queue


OLD_ROOT_SCREENSHOT_DIR = "/data/data/"
KEY_VIEW_HIERARCHY = "viewHierarchy"
KEY_AX_HIERARCHY = "axHierarchy"
KEY_CLASS = "class"
KEY_LEFT = "left"
KEY_TOP = "top"
KEY_WIDTH = "width"
KEY_HEIGHT = "height"
KEY_CHILDREN = "children"
DEFAULT_VIEW_CLASS = "android.view.View"


def usage():
    print(
        "usage: ./scripts/screenshot_tests/pull_screenshots com.facebook.apk.name.tests [--generate-png]",
        file=sys.stderr,
    )
    return


def sort_screenshots(screenshots):
    def sort_key(screenshot):
        group = screenshot.get("group")

        group = group if group is not None else ""

        return (group, screenshot["name"])

    return sorted(screenshots, key=sort_key)


def show_old_result(
    device_name,
    output_dir,
    test_name,
    html,
    new_screenshot,
    test_img_api,
    old_imgs_data,
):
    try:
        old_screenshot_url = "./" + test_name + "_expected.png"
        #     = get_old_screenshot_url(
        #     device_name, output_dir, test_name, test_img_api, old_imgs_data
        # )
        html.write('<div class="img-block">Expected')
        html.write('<div class="img-wrapper">')
        html.write('<img src="%s"></img>' % old_screenshot_url)
        html.write("</div>")
        html.write("</div>")
    except Exception:
        # Do nothing
        pass


def get_old_screenshot_url(device_name, output_dir, test_name, test_img_api, old_imgs_data):
    return join(test_img_api, device_name + "/" + test_name + ".png")
    # return "./" + test_name + "_expected.png"
    # old_imgs_data["test"] = test_name
    # encoded_data = urllib.urlencode(old_imgs_data)
    # url = test_img_api + encoded_data
    # response = json.loads(urllib.urlopen(url).read().decode("utf-8"))
    # if "error" in response:
    #     raise Exception
    # return response["url"]


def generate_html(
    output_dir,
    test_img_api=None,
    old_imgs_data=None,
    diff=False,
    device_name=''
):
    # Take in:
    # output_dir a directory with imgs and data outputted by the just-run test,
    # test_img_api a url that takes in the name of the test and a dict w/ data,
    #   and returns a url to an image from a previous run of the test,
    # old_imgs_data a dict that will be used in the test_img_api url.
    # Creates the html for showing a before and after comparison of the images.
    screenshots = json.load(open(join(output_dir, "metadata.json")))
    alternate = False
    index_html = abspath(join(output_dir, "index.html"))
    with codecs.open(index_html, mode="w", encoding="utf-8") as html:
        html.write("<!DOCTYPE html>")
        html.write("<html>")
        html.write("<head>")
        html.write("<title>Screenshot Test Results</title>")
        html.write(
            '<script src="https://ajax.googleapis.com/ajax/libs/jquery/2.1.3/jquery.min.js"></script>'
        )
        html.write(
            '<script src="https://ajax.googleapis.com/ajax/libs/jqueryui/1.11.3/jquery-ui.min.js"></script>'
        )
        html.write('<script src="default.js"></script>')
        html.write(
            '<link rel="stylesheet" href="https://ajax.googleapis.com/ajax/libs/jqueryui/1.11.3/themes/smoothness/jquery-ui.css" />'
        )
        html.write('<link rel="stylesheet" href="default.css"></head>')
        html.write("<body>")

        html.write("<style>")
        html.write(".img-block {")
        html.write("max-width: 15%; max-height: 50%;")
        html.write("}")
        html.write("img {")
        html.write("max-width: 100%; max-height: 100%;")
        html.write("}")
        html.write(".command-wrapper {")
        html.write("max-width: 100%; max-height: 100%;")
        html.write("}")
        html.write("</style>")

        screenshot_num = 0
        for screenshot in sort_screenshots(screenshots):
            screenshot_num += 1
            alternate = not alternate
            canonical_name = screenshot["name"]
            package = ""
            name = canonical_name
            if "." in canonical_name:
                last_seperator = canonical_name.rindex(".") + 1
                package = canonical_name[:last_seperator]
                name = canonical_name[last_seperator:]

            html.write(
                '<div class="screenshot %s">' % ("alternate" if alternate else "")
            )
            html.write('<div class="screenshot_name">')
            html.write('<span class="demphasize">%s</span>%s' % (package, name))
            html.write("</div>")

            group = screenshot.get("group")
            if group:
                html.write('<div class="screenshot_group">%s</div>' % group)

            extras = screenshot.get("extras")
            if extras is not None:
                str = ""
                for key, value in extras:
                    if key is not None:
                        str = str + "*****" + key + "*****\n\n" + value + "\n\n\n"
                if str != "":
                    extra_html = (
                        '<button class="extra" data="%s">Extra info</button>' % str
                    )
                    html.write(extra_html.encode("utf-8").strip())

            description = screenshot.get("description")
            if description is not None:
                html.write('<div class="screenshot_description">%s</div>' % description)

            error = screenshot.get("error")
            if error is not None:
                html.write('<div class="screenshot_error">%s</div>' % error)
            else:
                hierarchy_data = get_view_hierarchy(output_dir, screenshot)
                if hierarchy_data and KEY_VIEW_HIERARCHY in hierarchy_data:
                    hierarchy = hierarchy_data[KEY_VIEW_HIERARCHY]
                    ax_hierarchy = hierarchy_data[KEY_AX_HIERARCHY]
                else:
                    hierarchy = hierarchy_data
                    ax_hierarchy = None

                html.write('<div class="flex-wrapper">')
                comparing = test_img_api is not None and old_imgs_data is not None
                if comparing:
                    show_old_result(
                        device_name,
                        output_dir,
                        canonical_name,
                        html,
                        screenshot,
                        test_img_api,
                        old_imgs_data,
                    )
                write_image(
                    hierarchy,
                    output_dir,
                    html,
                    screenshot,
                    screenshot_num,
                    comparing,
                )
                    # try:
                if comparing and diff == "true":
                    old_screenshot_url = get_old_screenshot_url(
                        device_name, output_dir, canonical_name, test_img_api, old_imgs_data
                    )
                    write_image_diff(
                        old_screenshot_url, output_dir, html, screenshot
                    )
                    # except Exception:
                    #     # Do nothing
                    #     pass

                html.write('<div class="command-wrapper">')
                write_commands(html)
                write_view_hierarchy(hierarchy, html, screenshot_num)
                write_ax_hierarchy(ax_hierarchy, html, screenshot_num)
                html.write("</div>")
                html.write("</div>")

            html.write("</div>")
            html.write('<div class="clearfix"></div>')
            html.write("<hr/>")

        html.write("</body></html>")
        return index_html


def write_commands(html):
    html.write('<button class="toggle_dark">Toggle Dark Background</button>')
    html.write(
        '<button class="toggle_hierarchy">Toggle View Hierarchy Overlay</button>'
    )


def write_view_hierarchy(hierarchy, html, parent_id):
    if not hierarchy:
        return

    html.write("<h3>View Hierarchy</h3>")
    html.write('<div class="view-hierarchy">')
    write_view_hierarchy_tree_node(hierarchy, html, parent_id, True)
    html.write("</div>")


def write_ax_hierarchy(hierarchy, html, parent_id):
    if not hierarchy:
        return

    html.write("<h3>Accessibility Hierarchy</h3>")
    html.write('<div class="view-hierarchy">')
    write_view_hierarchy_tree_node(hierarchy, html, parent_id, False)
    html.write("</div>")


def write_view_hierarchy_tree_node(node, html, parent_id, with_overlay_target):
    if with_overlay_target:
        html.write(
            '<details target="#%s-%s">'
            % (parent_id, get_view_hierarchy_overlay_node_id(node))
        )
    else:
        html.write("<details>")
    html.write("<summary>%s</summary>" % node.get(KEY_CLASS, DEFAULT_VIEW_CLASS))
    html.write("<ul>")
    for item in sorted(node):
        if item == KEY_CHILDREN or item == KEY_CLASS:
            continue
        html.write("<li><strong>%s:</strong> %s</li>" % (item, node[item]))

    html.write("</ul>")
    if KEY_CHILDREN in node and node[KEY_CHILDREN]:
        for child in node[KEY_CHILDREN]:
            write_view_hierarchy_tree_node(child, html, parent_id, with_overlay_target)

    html.write("</details>")


def write_view_hierarchy_overlay_nodes(hierarchy, html, parent_id):
    if not hierarchy:
        return

    to_output = Queue()
    to_output.put(hierarchy)
    while not to_output.empty():
        node = to_output.get()
        left = (node[KEY_LEFT]) #/ 1080 * 100
        top = (node[KEY_TOP]) #/ 19290 * 100
        width = (node[KEY_WIDTH] - 4)
        height = (node[KEY_HEIGHT] - 4)
        # width = float(node[KEY_WIDTH] - 0) #/ 1080 * 100
        # height = float(node[KEY_HEIGHT] - 0) #/ 1920 * 100
        id = get_view_hierarchy_overlay_node_id(node)
        node_html = """
        <div
          class="hierarchy-node"
          style="left:%d%s;top:%d%s;width:%d%s;height:%d%s;"
          id="%s-%s"></div>
        """
        format = 'px'
        html.write(node_html % (left, format, top,format, width, format, height, format, parent_id, id))

        if KEY_CHILDREN in node:
            for child in node[KEY_CHILDREN]:
                to_output.put(child)


def get_view_hierarchy_overlay_node_id(node):
    cls = node.get(KEY_CLASS, DEFAULT_VIEW_CLASS)
    x = node[KEY_LEFT]
    y = node[KEY_TOP]
    width = node[KEY_WIDTH]
    height = node[KEY_HEIGHT]
    return "node-%s-%d-%d-%d-%d" % (cls.replace(".", "-"), x, y, width, height)


def get_view_hierarchy(dir, screenshot):
    json_path = join(dir, screenshot["name"] + "_dump.json")
    if not os.path.exists(json_path):
        return None
    with codecs.open(json_path, mode="r", encoding="utf-8") as dump:
        return json.loads(dump.read())


def write_image(hierarchy, dir, html, screenshot, parent_id, comparing):
    html.write('<div class="img-block">')
    if comparing:
        html.write("Actual")
    html.write('<div class="img-wrapper">')
    html.write("<table>")
    for y in range(int(screenshot["tileHeight"])):
        html.write("<tr>")
        for x in range(int(screenshot["tileWidth"])):
            html.write("<td>")
            image_file = "./" + common.get_image_file_name(screenshot["name"], x, y)

            if os.path.exists(join(dir, image_file)):
                html.write('<img src="%s" />' % image_file)

            html.write("</td>")
        html.write("</tr>")
    html.write("</table>")
    html.write('<div class="hierarchy-overlay">')
    write_view_hierarchy_overlay_nodes(hierarchy, html, parent_id)
    html.write("</div></div></div>")


def write_image_diff(old_screenshot_url, dir, html, screenshot):
    from PIL import Image, ImageChops, ImageOps, ImageDraw

    old_image = Image.open(urllib.urlopen(old_screenshot_url))
    new_image = Image.new(old_image.mode, (old_image.size[0], old_image.size[1]))

    # combine all tiles back into one image to ease the comparison
    x_offset = y_offset = height = 0
    for y in range(int(screenshot["tileHeight"])):
        for x in range(int(screenshot["tileWidth"])):
            image_file = join(
                dir, "./" + common.get_image_file_name(screenshot["name"], x, y)
            )
            if os.path.exists(image_file):
                img = Image.open(image_file)
                new_image.paste(img, (x_offset, y_offset))
                x_offset += img.size[0]
                height = img.size[1]
        x_offset = 0
        y_offset += height
    difference = ImageChops.difference(old_image, new_image)#.convert("RGB")
    # difference = ImageOps.invert(difference)

    # with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as fp:
        # difference.save(fp)
    diff = difference.getbbox()
    # raise Exception(diff)
    if diff:
        diff_list = list(diff) if diff else []
        draw = ImageDraw.Draw(new_image)
        draw.rectangle(diff_list, outline=(255, 0, 0))
        diff_rect_name = screenshot["name"] + "_diff_rect.png"
        diff_name = join(dir, diff_rect_name)
        new_image.save(diff_name)
        # difference.save(diff_name)
        # new_image.close()
        html.write('<div class="img-block">')
        html.write("Diff Rectangle")
        html.write('<div class="img-wrapper">')
        html.write('<img src="%s" />' % join('.', diff_rect_name))
        html.write("</div></div>")

        diff_rgb_name = screenshot["name"] + "_diff_rgb.png"
        diff_name = join(dir, diff_rgb_name)
        new_image.save(diff_name)
        difference.convert("RGB").save(diff_name)
        html.write('<div class="img-block">')
        html.write("Diff RGB")
        html.write('<div class="img-wrapper">')
        html.write('<img src="%s" />' % join('.', diff_rgb_name))
        html.write("</div></div>")
        return False
    else:
        return True


def test_for_wkhtmltoimage():
    if subprocess.call(["which", "wkhtmltoimage"]) != 0:
        raise RuntimeError(
            """Could not find wkhtmltoimage in your path, we need this for generating pngs
Download an appropriate version from:
    http://wkhtmltopdf.org/downloads.html"""
        )


def generate_png(path_to_html, path_to_png):
    test_for_wkhtmltoimage()
    subprocess.check_call(
        ["wkhtmltoimage", path_to_html, path_to_png], stdout=sys.stdout
    )


def copy_assets(destination):
    """Copy static assets required for rendering the HTML"""
    _copy_asset("default.css", destination)
    _copy_asset("default.js", destination)
    _copy_asset("background.png", destination)
    _copy_asset("background_dark.png", destination)


def _copy_asset(filename, destination):
    thisdir = os.path.dirname(__file__)
    _copy_file(abspath(join(thisdir, filename)), join(destination, filename))


def _copy_file(src, dest):
    if os.path.exists(src):
        shutil.copyfile(src, dest)
    else:
        _copy_via_zip(src, None, dest)


def _copy_via_zip(src_zip, zip_path, dest):
    if os.path.exists(src_zip):
        zip = zipfile.ZipFile(src_zip)
        input = zip.open(zip_path, "r")
        with open(dest, "wb") as output:
            output.write(input.read())
    else:
        # walk up the tree
        head, tail = os.path.split(src_zip)

        _copy_via_zip(head, tail if not zip_path else (tail + "/" + zip_path), dest)


def _android_path_join_two(a, b):
    if b.startswith("/"):
        return b

    if not a.endswith("/"):
        a += "/"

    return a + b


def android_path_join(a, *args):
    """Similar to os.path.join(), but might differ in behavior on Windows"""

    if args == []:
        return a

    if len(args) == 1:
        return _android_path_join_two(a, args[0])

    return android_path_join(android_path_join(a, args[0]), *args[1:])


def pull_metadata(package, dir, adb_puller):
    root_screenshot_dir = android_path_join(
        adb_puller.get_external_data_dir(), "screenshots"
    )
    metadata_file = android_path_join(
        root_screenshot_dir, package, "screenshots-default/metadata.json"
    )

    old_metadata_file = android_path_join(
        OLD_ROOT_SCREENSHOT_DIR, package, "app_screenshots-default/metadata.json"
    )

    if adb_puller.remote_file_exists(metadata_file):
        adb_puller.pull(metadata_file, join(dir, "metadata.json"))
    elif adb_puller.remote_file_exists(old_metadata_file):
        adb_puller.pull(old_metadata_file, join(dir, "metadata.json"))
        metadata_file = old_metadata_file
    else:
        create_empty_metadata_file(dir)

    return metadata_file.replace("metadata.json", "")


def create_empty_metadata_file(dir):
    with open(join(dir, "metadata.json"), "w") as out:
        out.write("{}")


def pull_images(dir, device_dir, test_run_id, adb_puller):
    if adb_puller.remote_file_exists(android_path_join(device_dir, test_run_id)):
        bundle_name_local_file = join(dir, os.path.basename(test_run_id))

        # Optimization to pull down all the screenshots in a single pull.
        # If this file exists, we assume all of the screenshots are inside it.
        adb_puller.pull(
            android_path_join(device_dir, test_run_id), bundle_name_local_file
        )

        move_all_files_to_different_directory(bundle_name_local_file, dir)
        # clean up
        shutil.rmtree(bundle_name_local_file)


def pull_all(package, dir, test_run_id, adb_puller):
    device_dir = pull_metadata(package, dir, adb_puller=adb_puller)
    pull_images(dir, device_dir, test_run_id, adb_puller=adb_puller)


def pull_filtered(package, dir, adb_puller, test_run_id, filter_name_regex=None):
    device_dir = pull_metadata(package, dir, adb_puller=adb_puller)
    _validate_metadata(dir)
    metadata.filter_screenshots(
        join(dir, "metadata.json"), name_regex=filter_name_regex
    )
    pull_images(dir, device_dir, test_run_id, adb_puller=adb_puller)


def move_all_files_to_different_directory(source_dir, target_dir):
    file_names = os.listdir(source_dir)
    for file_name in file_names:
        shutil.move(
            os.path.join(source_dir, file_name), os.path.join(target_dir, file_name)
        )


def _summary(dir):
    metadataJson = json.load(open(join(dir, "metadata.json")))
    count = len(metadataJson)
    print("Found %d screenshots" % count)


def _validate_metadata(dir):
    try:
        with open(join(dir, "metadata.json"), "r") as f:
            json.loads(f.read())
    except Exception as e:
        raise RuntimeError(
            "Unable to parse metadata file, this commonly happens if you did not call ScreenshotRunner.onDestroy() from your instrumentation",
            e,
        )


def pull_screenshots(
    process,
    adb_puller,
    device_name_calculator=None,
    perform_pull=True,
    temp_dir=None,
    filter_name_regex=None,
    record=None,
    verify=None,
    test_run_id=None,
    opt_generate_png=None,
    test_img_api=None,
    old_imgs_data=None,
    failure_dir=None,
    diff=False,
    open_html=False,
):

    if not perform_pull and temp_dir is None:
        raise RuntimeError(
            """You must supply a directory for temp_dir if --no-pull is present"""
        )
    if not perform_pull and test_run_id is None:
        raise RuntimeError("""You must supply a test run id if --no-pull is present""")

    temp_dir = temp_dir or tempfile.mkdtemp(prefix="screenshots")

    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)

    copy_assets(temp_dir)

    if perform_pull is True:
        pull_filtered(
            process,
            adb_puller=adb_puller,
            dir=temp_dir,
            test_run_id=test_run_id,
            filter_name_regex=filter_name_regex,
        )

    _validate_metadata(temp_dir)
    device_name = device_name_calculator.name() if device_name_calculator else None
    path_to_html = ''
    if verify:
        path_to_html = generate_html(temp_dir, test_img_api, old_imgs_data, diff, device_name)
    record_dir = join(record, device_name) if record and device_name else record
    verify_dir = join(verify, device_name) if verify and device_name else verify
    if failure_dir:
        failure_dir = join(failure_dir, device_name) if device_name else failure_dir
        if not os.path.exists(failure_dir):
            os.makedirs(failure_dir)

    has_failures = False
    if record or verify:
        # don't import this early, since we need PIL to import this
        from .recorder import Recorder

        recorder = Recorder(temp_dir, record_dir or verify_dir, failure_dir, temp_dir)
        if verify:
            has_failures = recorder.verify()
        else:
            recorder.record()

    if opt_generate_png:
        generate_png(path_to_html, opt_generate_png)
        shutil.rmtree(temp_dir)
    else:
        print("\n\n")
        _summary(temp_dir)
        print("Open the following url in a browser to view the results: ")
        full_path = "file://" + path_to_html
        print("  %s" % full_path)
        print("\n\n")
        return Exception("screenshots are not same") if has_failures else None, full_path
        # if has_failures:
        #     return Exception("screenshots are not same")
        # else:
        #     return full_path


def setup_paths():
    android_home = common.get_android_sdk()
    os.environ["PATH"] = os.environ["PATH"] + ":" + android_home + "/platform-tools/"


def main(argv):
    setup_paths()
    try:
        opt_list, rest_args = getopt.gnu_getopt(
            argv[1:],
            "eds:",
            [
                "generate-png=",
                "filter-name-regex=",
                "apk",
                "record=",
                "verify=",
                "failure-dir=",
                "temp-dir=",
                "no-pull",
                "multiple-devices=",
                "test-run-id=",
                "open-html=",
                "diff=",
                "test_img_api=",
                "old_imgs_data="
            ],
        )
    except getopt.GetoptError:
        usage()
        return 2

    if len(rest_args) != 1:
        usage()
        return 2

    process = rest_args[0]  # something like com.facebook.places.tests

    opts = dict(opt_list)

    if "--apk" in opts:
        # treat process as an apk instead
        process = aapt.get_package(process)

    should_perform_pull = "--no-pull" not in opts

    multiple_devices = opts.get("--multiple-devices")
    device_calculator = (
        DeviceNameCalculator() if multiple_devices else NoOpDeviceNameCalculator()
    )

    base_puller_args = []
    if "-e" in opts:
        base_puller_args.append("-e")

    if "-d" in opts:
        base_puller_args.append("-d")

    if "-s" in opts:
        passed_serials = [opts["-s"]]
    elif "ANDROID_SERIAL" in os.environ:
        passed_serials = os.environ.get("ANDROID_SERIAL").split(",")
    else:
        passed_serials = common.get_connected_devices()

    # if passed_serials:
    #     puller_args_list = [
    #         base_puller_args + ["-s", serial] for serial in passed_serials
    #     ]
    # else:
    #     puller_args_list = [base_puller_args]

    puller_args_list = []
    device_calculator_list = []
    for serial in (passed_serials or []):
        puller_args_list.append(base_puller_args + ["-s", serial])
        device_calculator_list.append(DeviceNameCalculator(args=["-s", serial]) if multiple_devices else NoOpDeviceNameCalculator())
    if not len(puller_args_list):
        puller_args_list.append(base_puller_args)
        device_calculator_list.append(NoOpDeviceNameCalculator())

    test_results = []
    for index, puller_args in enumerate(puller_args_list):
        test_results.append(pull_screenshots(
            process,
            perform_pull=should_perform_pull,
            temp_dir=join(opts.get("--temp-dir"), device_calculator_list[index].name()),
            filter_name_regex=opts.get("--filter-name-regex"),
            opt_generate_png=opts.get("--generate-png"),
            test_run_id=opts.get("--test-run-id"),
            record=opts.get("--record"),
            verify=opts.get("--verify"),
            adb_puller=SimplePuller(puller_args),
            device_name_calculator=device_calculator_list[index],
            failure_dir=opts.get("--failure-dir"),
            open_html=opts.get("--open-html"),
            diff=opts.get("--diff"),
            old_imgs_data=opts.get("--old_imgs_data"),
            test_img_api=opts.get("--test_img_api")
        ))


    failures = filter(filterFailures, test_results)
    if opts.get("--open-html"):
        for html in test_results:
            if platform.system() == "Darwin":  # macOS
                subprocess.call(("open", html[1]))
            elif platform.system() == "Windows":  # Windows
                os.startfile(html[1])

    if failures:
        raise failures[0]

    # for result in test_results:
    #         if type(result) == Exception:
    #             raise result
    #         elif isinstance(result, basestring) and opts.get("--open-html"):
    #             if platform.system() == "Darwin":  # macOS
    #                 subprocess.call(("open", result))
    #             elif platform.system() == "Windows":  # Windows
    #                 os.startfile(result)

def filterFailures(obj):
    return obj[0] is not None

def filterHtmls(obj):
    return obj[1] is None

if __name__ == "__main__":
    sys.exit(main(sys.argv))










#
#
#
#
# #!/usr/bin/env python
# # Copyright (c) Facebook, Inc. and its affiliates.
# #
# # Licensed under the Apache License, Version 2.0 (the "License");
# # you may not use this file except in compliance with the License.
# # You may obtain a copy of the License at
# #
# #     http://www.apache.org/licenses/LICENSE-2.0
# #
# # Unless required by applicable law or agreed to in writing, software
# # distributed under the License is distributed on an "AS IS" BASIS,
# # WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# # See the License for the specific language governing permissions and
# # limitations under the License.
#
# from __future__ import absolute_import
# from __future__ import division
# from __future__ import print_function
# from __future__ import unicode_literals
#
# import codecs
# import getopt
# import json
# import shutil
# import subprocess, os, platform
# import sys
# import tempfile
# import urllib
# import xml.etree.ElementTree as ET
# import zipfile
# from os.path import abspath
# from os.path import join
#
# from . import aapt
# from . import common
# from . import metadata
# from .device_name_calculator import DeviceNameCalculator
# from .no_op_device_name_calculator import NoOpDeviceNameCalculator
# from .simple_puller import SimplePuller
#
# try:
#     from Queue import Queue
# except ImportError:
#     from queue import Queue
#
#
# OLD_ROOT_SCREENSHOT_DIR = "/data/data/"
# KEY_VIEW_HIERARCHY = "viewHierarchy"
# KEY_AX_HIERARCHY = "axHierarchy"
# KEY_CLASS = "class"
# KEY_LEFT = "left"
# KEY_TOP = "top"
# KEY_WIDTH = "width"
# KEY_HEIGHT = "height"
# KEY_CHILDREN = "children"
# DEFAULT_VIEW_CLASS = "android.view.View"
#
#
# def usage():
#     print(
#         "usage: ./scripts/screenshot_tests/pull_screenshots com.facebook.apk.name.tests [--generate-png]",
#         file=sys.stderr,
#     )
#     return
#
#
# def sort_screenshots(screenshots):
#     def sort_key(screenshot):
#         group = screenshot.get("group")
#
#         group = group if group is not None else ""
#
#         return (group, screenshot["name"])
#
#     return sorted(screenshots, key=sort_key)
#
#
# def show_old_result(
#         device_name,
#         output_dir,
#         test_name,
#         html,
#         new_screenshot,
#         test_img_api,
#         old_imgs_data,
# ):
#     try:
#         old_screenshot_url = get_old_screenshot_url(
#             device_name, output_dir, test_name, test_img_api, old_imgs_data
#         )
#         html.write('<div class="img-block">Current')
#         html.write('<div class="img-wrapper">')
#         html.write('<img src="%s"></img>' % old_screenshot_url)
#         html.write("</div>")
#         html.write("</div>")
#     except Exception:
#         # Do nothing
#         pass
#
#
# def get_old_screenshot_url(device_name, output_dir, test_name, test_img_api, old_imgs_data):
#     return join(test_img_api,device_name + "/" + test_name + ".png")
#     # old_imgs_data["test"] = test_name
#     # encoded_data = urllib.urlencode(old_imgs_data)
#     # url = test_img_api + encoded_data
#     # response = json.loads(urllib.urlopen(url).read().decode("utf-8"))
#     # if "error" in response:
#     #     raise Exception
#     # return response["url"]
#
#
# def generate_html(
#         output_dir,
#         test_img_api=None,
#         old_imgs_data=None,
#         diff=False,
#         device_name=''
# ):
#     # Take in:
#     # output_dir a directory with imgs and data outputted by the just-run test,
#     # test_img_api a url that takes in the name of the test and a dict w/ data,
#     #   and returns a url to an image from a previous run of the test,
#     # old_imgs_data a dict that will be used in the test_img_api url.
#     # Creates the html for showing a before and after comparison of the images.
#     screenshots = json.load(open(join(output_dir, "metadata.json")))
#     alternate = False
#     index_html = abspath(join(output_dir, "index.html"))
#     with codecs.open(index_html, mode="w", encoding="utf-8") as html:
#         html.write("<!DOCTYPE html>")
#         html.write("<html>")
#         html.write("<head>")
#         html.write("<title>Screenshot Test Results</title>")
#         html.write(
#             '<script src="https://ajax.googleapis.com/ajax/libs/jquery/2.1.3/jquery.min.js"></script>'
#         )
#         html.write(
#             '<script src="https://ajax.googleapis.com/ajax/libs/jqueryui/1.11.3/jquery-ui.min.js"></script>'
#         )
#         html.write('<script src="default.js"></script>')
#         html.write(
#             '<link rel="stylesheet" href="https://ajax.googleapis.com/ajax/libs/jqueryui/1.11.3/themes/smoothness/jquery-ui.css" />'
#         )
#         html.write('<link rel="stylesheet" href="default.css"></head>')
#         html.write("<body>")
#
#         html.write("<style>")
#         html.write(".img-block {")
#         html.write("max-width: 30%; max-height: 50%;")
#         html.write("}")
#         html.write("img {")
#         html.write("max-width: 100%; max-height: 100%;")
#         html.write("}")
#         html.write(".command-wrapper {")
#         html.write("max-width: 100%; max-height: 100%;")
#         html.write("}")
#         html.write("</style>")
#
#         screenshot_num = 0
#         for screenshot in sort_screenshots(screenshots):
#             screenshot_num += 1
#             alternate = not alternate
#             canonical_name = screenshot["name"]
#             package = ""
#             name = canonical_name
#             if "." in canonical_name:
#                 last_seperator = canonical_name.rindex(".") + 1
#                 package = canonical_name[:last_seperator]
#                 name = canonical_name[last_seperator:]
#
#             html.write(
#                 '<div class="screenshot %s">' % ("alternate" if alternate else "")
#             )
#             html.write('<div class="screenshot_name">')
#             html.write('<span class="demphasize">%s</span>%s' % (package, name))
#             html.write("</div>")
#
#             group = screenshot.get("group")
#             if group:
#                 html.write('<div class="screenshot_group">%s</div>' % group)
#
#             extras = screenshot.get("extras")
#             if extras is not None:
#                 str = ""
#                 for key, value in extras:
#                     if key is not None:
#                         str = str + "*****" + key + "*****\n\n" + value + "\n\n\n"
#                 if str != "":
#                     extra_html = (
#                             '<button class="extra" data="%s">Extra info</button>' % str
#                     )
#                     html.write(extra_html.encode("utf-8").strip())
#
#             description = screenshot.get("description")
#             if description is not None:
#                 html.write('<div class="screenshot_description">%s</div>' % description)
#
#             error = screenshot.get("error")
#             if error is not None:
#                 html.write('<div class="screenshot_error">%s</div>' % error)
#             else:
#                 hierarchy_data = get_view_hierarchy(output_dir, screenshot)
#                 if hierarchy_data and KEY_VIEW_HIERARCHY in hierarchy_data:
#                     hierarchy = hierarchy_data[KEY_VIEW_HIERARCHY]
#                     ax_hierarchy = hierarchy_data[KEY_AX_HIERARCHY]
#                 else:
#                     hierarchy = hierarchy_data
#                     ax_hierarchy = None
#
#                 html.write('<div class="flex-wrapper">')
#                 comparing = test_img_api is not None and old_imgs_data is not None
#                 if comparing:
#                     show_old_result(
#                         device_name,
#                         output_dir,
#                         canonical_name,
#                         html,
#                         screenshot,
#                         test_img_api,
#                         old_imgs_data,
#                     )
#                 write_image(
#                     hierarchy,
#                     output_dir,
#                     html,
#                     screenshot,
#                     screenshot_num,
#                     comparing,
#                 )
#                 # try:
#                 if comparing and diff == "true":
#                     old_screenshot_url = get_old_screenshot_url(
#                         device_name, output_dir, canonical_name, test_img_api, old_imgs_data
#                     )
#                     write_image_diff(
#                         old_screenshot_url, output_dir, html, screenshot
#                     )
#                     # except Exception:
#                     #     # Do nothing
#                     #     pass
#
#                 html.write('<div class="command-wrapper">')
#                 write_commands(html)
#                 write_view_hierarchy(hierarchy, html, screenshot_num)
#                 write_ax_hierarchy(ax_hierarchy, html, screenshot_num)
#                 html.write("</div>")
#                 html.write("</div>")
#
#             html.write("</div>")
#             html.write('<div class="clearfix"></div>')
#             html.write("<hr/>")
#
#         html.write("</body></html>")
#         return index_html
#
#
# def write_commands(html):
#     html.write('<button class="toggle_dark">Toggle Dark Background</button>')
#     html.write(
#         '<button class="toggle_hierarchy">Toggle View Hierarchy Overlay</button>'
#     )
#
#
# def write_view_hierarchy(hierarchy, html, parent_id):
#     if not hierarchy:
#         return
#
#     html.write("<h3>View Hierarchy</h3>")
#     html.write('<div class="view-hierarchy">')
#     write_view_hierarchy_tree_node(hierarchy, html, parent_id, True)
#     html.write("</div>")
#
#
# def write_ax_hierarchy(hierarchy, html, parent_id):
#     if not hierarchy:
#         return
#
#     html.write("<h3>Accessibility Hierarchy</h3>")
#     html.write('<div class="view-hierarchy">')
#     write_view_hierarchy_tree_node(hierarchy, html, parent_id, False)
#     html.write("</div>")
#
#
# def write_view_hierarchy_tree_node(node, html, parent_id, with_overlay_target):
#     if with_overlay_target:
#         html.write(
#             '<details target="#%s-%s">'
#             % (parent_id, get_view_hierarchy_overlay_node_id(node))
#         )
#     else:
#         html.write("<details>")
#     html.write("<summary>%s</summary>" % node.get(KEY_CLASS, DEFAULT_VIEW_CLASS))
#     html.write("<ul>")
#     for item in sorted(node):
#         if item == KEY_CHILDREN or item == KEY_CLASS:
#             continue
#         html.write("<li><strong>%s:</strong> %s</li>" % (item, node[item]))
#
#     html.write("</ul>")
#     if KEY_CHILDREN in node and node[KEY_CHILDREN]:
#         for child in node[KEY_CHILDREN]:
#             write_view_hierarchy_tree_node(child, html, parent_id, with_overlay_target)
#
#     html.write("</details>")
#
#
# def write_view_hierarchy_overlay_nodes(hierarchy, html, parent_id):
#     if not hierarchy:
#         return
#
#     to_output = Queue()
#     to_output.put(hierarchy)
#     while not to_output.empty():
#         node = to_output.get()
#         left = (node[KEY_LEFT]) #/ 1080 * 100
#         top = (node[KEY_TOP]) #/ 19290 * 100
#         width = (node[KEY_WIDTH] - 4)
#         height = (node[KEY_HEIGHT] - 4)
#         # width = float(node[KEY_WIDTH] - 0) #/ 1080 * 100
#         # height = float(node[KEY_HEIGHT] - 0) #/ 1920 * 100
#         id = get_view_hierarchy_overlay_node_id(node)
#         node_html = """
#         <div
#           class="hierarchy-node"
#           style="left:%d%s;top:%d%s;width:%d%s;height:%d%s;"
#           id="%s-%s"></div>
#         """
#         format = 'px'
#         html.write(node_html % (left, format, top,format, width, format, height, format, parent_id, id))
#
#         if KEY_CHILDREN in node:
#             for child in node[KEY_CHILDREN]:
#                 to_output.put(child)
#
#
# def get_view_hierarchy_overlay_node_id(node):
#     cls = node.get(KEY_CLASS, DEFAULT_VIEW_CLASS)
#     x = node[KEY_LEFT]
#     y = node[KEY_TOP]
#     width = node[KEY_WIDTH]
#     height = node[KEY_HEIGHT]
#     return "node-%s-%d-%d-%d-%d" % (cls.replace(".", "-"), x, y, width, height)
#
#
# def get_view_hierarchy(dir, screenshot):
#     json_path = join(dir, screenshot["name"] + "_dump.json")
#     if not os.path.exists(json_path):
#         return None
#     with codecs.open(json_path, mode="r", encoding="utf-8") as dump:
#         return json.loads(dump.read())
#
#
# def write_image(hierarchy, dir, html, screenshot, parent_id, comparing):
#     html.write('<div class="img-block">')
#     if comparing:
#         html.write("New Output")
#     html.write('<div class="img-wrapper">')
#     html.write("<table>")
#     for y in range(int(screenshot["tileHeight"])):
#         html.write("<tr>")
#         for x in range(int(screenshot["tileWidth"])):
#             html.write("<td>")
#             image_file = "./" + common.get_image_file_name(screenshot["name"], x, y)
#
#             if os.path.exists(join(dir, image_file)):
#                 html.write('<img src="%s" />' % image_file)
#
#             html.write("</td>")
#         html.write("</tr>")
#     html.write("</table>")
#     html.write('<div class="hierarchy-overlay">')
#     write_view_hierarchy_overlay_nodes(hierarchy, html, parent_id)
#     html.write("</div></div></div>")
#
#
# def write_image_diff(old_screenshot_url, dir, html, screenshot):
#     from PIL import Image, ImageChops, ImageOps, ImageDraw
#
#     old_image = Image.open(urllib.urlopen(old_screenshot_url))
#     new_image = Image.new(old_image.mode, (old_image.size[0], old_image.size[1]))
#
#     # combine all tiles back into one image to ease the comparison
#     x_offset = y_offset = height = 0
#     for y in range(int(screenshot["tileHeight"])):
#         for x in range(int(screenshot["tileWidth"])):
#             image_file = join(
#                 dir, "./" + common.get_image_file_name(screenshot["name"], x, y)
#             )
#             if os.path.exists(image_file):
#                 img = Image.open(image_file)
#                 new_image.paste(img, (x_offset, y_offset))
#                 x_offset += img.size[0]
#                 height = img.size[1]
#         x_offset = 0
#         y_offset += height
#
#     difference = ImageChops.difference(old_image, new_image).convert("RGB")
#     # difference = ImageOps.invert(difference)
#
#     # with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as fp:
#     # difference.save(fp)
#     diff = difference.getbbox()
#     if diff is not None:
#         diff_list = list(diff) if diff else []
#         draw = ImageDraw.Draw(new_image)
#         draw.rectangle(diff_list, outline=(255, 0, 0))
#         diff_name = join(dir, screenshot["name"] + "_diff.png")
#         # open(diff_name, 'w')
#         difference.save(diff_name)
#         # new_image.close()
#         html.write('<div class="img-block">')
#         html.write("Diff")
#         html.write('<div class="img-wrapper">')
#         html.write('<img src="%s" />' % diff_name)
#         html.write("</div></div>")
#         return False
#     return True
#
#
# def test_for_wkhtmltoimage():
#     if subprocess.call(["which", "wkhtmltoimage"]) != 0:
#         raise RuntimeError(
#             """Could not find wkhtmltoimage in your path, we need this for generating pngs
# Download an appropriate version from:
#     http://wkhtmltopdf.org/downloads.html"""
#         )
#
#
# def generate_png(path_to_html, path_to_png):
#     test_for_wkhtmltoimage()
#     subprocess.check_call(
#         ["wkhtmltoimage", path_to_html, path_to_png], stdout=sys.stdout
#     )
#
#
# def copy_assets(destination):
#     """Copy static assets required for rendering the HTML"""
#     _copy_asset("default.css", destination)
#     _copy_asset("default.js", destination)
#     _copy_asset("background.png", destination)
#     _copy_asset("background_dark.png", destination)
#
#
# def _copy_asset(filename, destination):
#     thisdir = os.path.dirname(__file__)
#     _copy_file(abspath(join(thisdir, filename)), join(destination, filename))
#
#
# def _copy_file(src, dest):
#     if os.path.exists(src):
#         shutil.copyfile(src, dest)
#     else:
#         _copy_via_zip(src, None, dest)
#
#
# def _copy_via_zip(src_zip, zip_path, dest):
#     if os.path.exists(src_zip):
#         zip = zipfile.ZipFile(src_zip)
#         input = zip.open(zip_path, "r")
#         with open(dest, "wb") as output:
#             output.write(input.read())
#     else:
#         # walk up the tree
#         head, tail = os.path.split(src_zip)
#
#         _copy_via_zip(head, tail if not zip_path else (tail + "/" + zip_path), dest)
#
#
# def _android_path_join_two(a, b):
#     if b.startswith("/"):
#         return b
#
#     if not a.endswith("/"):
#         a += "/"
#
#     return a + b
#
#
# def android_path_join(a, *args):
#     """Similar to os.path.join(), but might differ in behavior on Windows"""
#
#     if args == []:
#         return a
#
#     if len(args) == 1:
#         return _android_path_join_two(a, args[0])
#
#     return android_path_join(android_path_join(a, args[0]), *args[1:])
#
#
# def pull_metadata(package, dir, adb_puller):
#     root_screenshot_dir = android_path_join(
#         adb_puller.get_external_data_dir(), "screenshots"
#     )
#     metadata_file = android_path_join(
#         root_screenshot_dir, package, "screenshots-default/metadata.json"
#     )
#
#     old_metadata_file = android_path_join(
#         OLD_ROOT_SCREENSHOT_DIR, package, "app_screenshots-default/metadata.json"
#     )
#
#     if adb_puller.remote_file_exists(metadata_file):
#         adb_puller.pull(metadata_file, join(dir, "metadata.json"))
#     elif adb_puller.remote_file_exists(old_metadata_file):
#         adb_puller.pull(old_metadata_file, join(dir, "metadata.json"))
#         metadata_file = old_metadata_file
#     else:
#         create_empty_metadata_file(dir)
#
#     return metadata_file.replace("metadata.json", "")
#
#
# def create_empty_metadata_file(dir):
#     with open(join(dir, "metadata.json"), "w") as out:
#         out.write("{}")
#
#
# def pull_images(dir, device_dir, test_run_id, adb_puller):
#     if adb_puller.remote_file_exists(android_path_join(device_dir, test_run_id)):
#         bundle_name_local_file = join(dir, os.path.basename(test_run_id))
#
#         # Optimization to pull down all the screenshots in a single pull.
#         # If this file exists, we assume all of the screenshots are inside it.
#         adb_puller.pull(
#             android_path_join(device_dir, test_run_id), bundle_name_local_file
#         )
#
#         move_all_files_to_different_directory(bundle_name_local_file, dir)
#         # clean up
#         shutil.rmtree(bundle_name_local_file)
#
#
# def pull_all(package, dir, test_run_id, adb_puller):
#     device_dir = pull_metadata(package, dir, adb_puller=adb_puller)
#     pull_images(dir, device_dir, test_run_id, adb_puller=adb_puller)
#
#
# def pull_filtered(package, dir, adb_puller, test_run_id, filter_name_regex=None):
#     device_dir = pull_metadata(package, dir, adb_puller=adb_puller)
#     _validate_metadata(dir)
#     metadata.filter_screenshots(
#         join(dir, "metadata.json"), name_regex=filter_name_regex
#     )
#     pull_images(dir, device_dir, test_run_id, adb_puller=adb_puller)
#
#
# def move_all_files_to_different_directory(source_dir, target_dir):
#     file_names = os.listdir(source_dir)
#     for file_name in file_names:
#         shutil.move(
#             os.path.join(source_dir, file_name), os.path.join(target_dir, file_name)
#         )
#
#
# def _summary(dir):
#     metadataJson = json.load(open(join(dir, "metadata.json")))
#     count = len(metadataJson)
#     print("Found %d screenshots" % count)
#
#
# def _validate_metadata(dir):
#     try:
#         with open(join(dir, "metadata.json"), "r") as f:
#             json.loads(f.read())
#     except Exception as e:
#         raise RuntimeError(
#             "Unable to parse metadata file, this commonly happens if you did not call ScreenshotRunner.onDestroy() from your instrumentation",
#             e,
#         )
#
#
# def pull_screenshots(
#         process,
#         adb_puller,
#         device_name_calculator=None,
#         perform_pull=True,
#         temp_dir=None,
#         filter_name_regex=None,
#         record=None,
#         verify=None,
#         test_run_id=None,
#         opt_generate_png=None,
#         test_img_api=None,
#         old_imgs_data=None,
#         failure_dir=None,
#         diff=False,
#         open_html=False,
# ):
#
#     if not perform_pull and temp_dir is None:
#         raise RuntimeError(
#             """You must supply a directory for temp_dir if --no-pull is present"""
#         )
#     if not perform_pull and test_run_id is None:
#         raise RuntimeError("""You must supply a test run id if --no-pull is present""")
#
#     temp_dir = temp_dir or tempfile.mkdtemp(prefix="screenshots")
#
#     if not os.path.exists(temp_dir):
#         os.makedirs(temp_dir)
#
#     copy_assets(temp_dir)
#
#     if perform_pull is True:
#         pull_filtered(
#             process,
#             adb_puller=adb_puller,
#             dir=temp_dir,
#             test_run_id=test_run_id,
#             filter_name_regex=filter_name_regex,
#         )
#
#     _validate_metadata(temp_dir)
#     device_name = device_name_calculator.name() if device_name_calculator else None
#     path_to_html = ''
#     if verify:
#         path_to_html = generate_html(temp_dir, test_img_api, old_imgs_data, diff, device_name)
#     record_dir = join(record, device_name) if record and device_name else record
#     verify_dir = join(verify, device_name) if verify and device_name else verify
#     if failure_dir:
#         failure_dir = join(failure_dir, device_name) if device_name else failure_dir
#         if not os.path.exists(failure_dir):
#             os.makedirs(failure_dir)
#
#     has_failures = False
#     if record or verify:
#         # don't import this early, since we need PIL to import this
#         from .recorder import Recorder
#
#         recorder = Recorder(temp_dir, record_dir or verify_dir, failure_dir)
#         if verify:
#             has_failures = recorder.verify()
#         else:
#             recorder.record()
#
#     if opt_generate_png:
#         generate_png(path_to_html, opt_generate_png)
#         shutil.rmtree(temp_dir)
#     else:
#         print("\n\n")
#         _summary(temp_dir)
#         print("Open the following url in a browser to view the results: ")
#         full_path = "file://" + path_to_html
#         print("  %s" % full_path)
#         print("\n\n")
#         if has_failures:
#             raise Exception("screenshots are not same")
#         if open_html:
#             if platform.system() == "Darwin":  # macOS
#                 subprocess.call(("open", full_path))
#             elif platform.system() == "Windows":  # Windows
#                 os.startfile(full_path)
#
#
# def setup_paths():
#     android_home = common.get_android_sdk()
#     os.environ["PATH"] = os.environ["PATH"] + ":" + android_home + "/platform-tools/"
#
#
# def main(argv):
#     setup_paths()
#     try:
#         opt_list, rest_args = getopt.gnu_getopt(
#             argv[1:],
#             "eds:",
#             [
#                 "generate-png=",
#                 "filter-name-regex=",
#                 "apk",
#                 "record=",
#                 "verify=",
#                 "failure-dir=",
#                 "temp-dir=",
#                 "no-pull",
#                 "multiple-devices=",
#                 "test-run-id=",
#                 "open-html=",
#                 "diff=",
#                 "test_img_api=",
#                 "old_imgs_data="
#             ],
#         )
#     except getopt.GetoptError:
#         usage()
#         return 2
#
#     if len(rest_args) != 1:
#         usage()
#         return 2
#
#     process = rest_args[0]  # something like com.facebook.places.tests
#
#     opts = dict(opt_list)
#
#     if "--apk" in opts:
#         # treat process as an apk instead
#         process = aapt.get_package(process)
#
#     should_perform_pull = "--no-pull" not in opts
#
#     multiple_devices = opts.get("--multiple-devices")
#     device_calculator = (
#         DeviceNameCalculator() if multiple_devices else NoOpDeviceNameCalculator()
#     )
#
#     base_puller_args = []
#     if "-e" in opts:
#         base_puller_args.append("-e")
#
#     if "-d" in opts:
#         base_puller_args.append("-d")
#
#     if "-s" in opts:
#         passed_serials = [opts["-s"]]
#     elif "ANDROID_SERIAL" in os.environ:
#         passed_serials = os.environ.get("ANDROID_SERIAL").split(",")
#     else:
#         passed_serials = common.get_connected_devices()
#
#     if passed_serials:
#         puller_args_list = [
#             base_puller_args + ["-s", serial] for serial in passed_serials
#         ]
#     else:
#         puller_args_list = [base_puller_args]
#
#     for puller_args in puller_args_list:
#         pull_screenshots(
#             process,
#             perform_pull=should_perform_pull,
#             temp_dir=opts.get("--temp-dir"),
#             filter_name_regex=opts.get("--filter-name-regex"),
#             opt_generate_png=opts.get("--generate-png"),
#             test_run_id=opts.get("--test-run-id"),
#             record=opts.get("--record"),
#             verify=opts.get("--verify"),
#             adb_puller=SimplePuller(puller_args),
#             device_name_calculator=device_calculator,
#             failure_dir=opts.get("--failure-dir"),
#             open_html=opts.get("--open-html"),
#             diff=opts.get("--diff"),
#             old_imgs_data=opts.get("--old_imgs_data"),
#             test_img_api=opts.get("--test_img_api")
#         )
#
#
# if __name__ == "__main__":
#     sys.exit(main(sys.argv))

