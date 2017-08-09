# This class represents a Demo to be executed in SimDem.

import difflib
import os
import re
import sys
import urllib.request
from environment import Environment
from cli import Ui

class Demo(object):
    def __init__(self, ui, is_running_in_docker, script_dir="demo_scripts", filename="script.md", is_simulation=True, is_automated=False, is_testing=False, is_fast_fail=True,is_learning = False, is_prerequisite = False):
        """Initialize variables"""
        self.ui = ui
        self.is_docker = is_running_in_docker
        self.filename = filename
        self.script_dir = script_dir
        self.is_simulation = is_simulation
        self.is_automated = is_automated
        self.is_testing = is_testing
        self.is_fast_fail = is_fast_fail
        self.is_learning = is_learning
        self.current_command = ""
        self.current_description = ""
        self.last_command = ""
        self.is_prerequisite = is_prerequisite
        
    def get_current_command(self):
        """
        Return a tuple of the current command and a list of environment
        variables that haven't been set.
        """
        var_pattern = re.compile(".*?(?<=\$)\(?{?(\w*)(?=[\W|\$|\s|\\\"]?)\)?(?!\$).*")
        matches = var_pattern.findall(self.current_command)
        var_list = []
        if matches:
            for var in matches:
                if len(var) > 0:
                    value = self.ui.get_shell(self).run_command("echo $" + var).strip()
                    if len(value) == 0 and not '$(' + var in self.current_command:
                        var_list.append(var)
        return self.current_command, var_list

    def get_scripts(self, directory):
        """
        Starting with the supplied directory find all `script.md` files
        and return them as a list of scripts available to this execution.
        We will not return multiple `script.md` files from each part of 
        the tree. It is assumed that the highest level `script.md` files
        contains an index of scripts in that directory.

        """
        lines = []
        for dirpath, dirs, files in os.walk(directory):
            for file in files:
                if file == "script.md":                                
                    lines.append(os.path.join(dirpath[len(directory):], file) + "\n")
                
        return lines

    def generate_toc(self):
        toc = {}
        lines = []
        lines.append("# Welcome to Simdem\n")
        lines.append("Below is an autogenerated list of scripts available in `" + self.script_dir + "` and its subdirectories. You can execute any of them from here.\n\n")
        lines.append("# Next Steps\n")

        scripts = self.get_scripts(self.script_dir)

        for script in scripts:
            script = script.strip()
            with open(os.path.join(self.script_dir, script)) as f:
                title = f.readline().strip()
                title = title[2:]
            demo = { "title": title, "path": script }
                
            name = script[:script.index(os.sep)]
            if not name.endswith(".md") and name not in toc:
                toc[name] = [ demo ]
            elif name in toc:
                demos = toc[name]
                demos.append(demo)
                toc[name] = demos

        idx = 1
        for item in sorted(toc):
            demos = toc[item]
            for demo in demos:
                lines.append("  " + str(idx) + ". [" + item + " / " + demo["title"] + "](" + demo["path"] + ")\n")
                idx += 1

        return lines
    
    def run(self):
        """
        Reads a script.md file in the indicated directoy and runs the
        commands contained within. If simulation == True then human
        entry will be simulated (looks like typing and waits for
        keyboard input before proceeding to the next command). This is
        useful if you want to run a fully automated demo.

        The script.md file will be parsed as follows:

        ``` marks the start or end of a code block

        Each line in a code block will be treated as a separate command.
        All other lines will be ignored
        """
        self.env = Environment(self.script_dir, is_test = self.is_testing)

        if not self.script_dir.endswith('/'):
            self.script_dir = self.script_dir + "/"

        lines = None
        
        if self.is_testing:
            test_file = self.script_dir + "test_plan.txt"
            if os.path.isfile(test_file):
                plan_lines = list(open(test_file))
                lines = []
                for line in plan_lines:
                    line = line.strip()
                    if not line.startswith("#"):
                        # not a comment so should be a path to a script with tests
                        if not line == "":
                            file = self.script_dir + line
                            lines = lines + list(open(file))

        file = self.script_dir + self.filename

        if file.startswith("http"):
            # FIXME: Error handling
            response = urllib.request.urlopen(file)
            data = response.read().decode("utf-8")
            lines = data.splitlines(True)
        else:
            if not lines and os.path.isfile(file):
                lines = list(open(file))
            elif not lines:
                lines = self.generate_toc()

        classified_lines = self.classify_lines(lines)
        failed_tests, passed_tests = self.execute(classified_lines)

        if self.is_testing:
            self.ui.horizontal_rule()
            self.ui.heading("Test Results")
            if failed_tests > 0:
                self.ui.warning("Failed Tests: " + str(failed_tests))
                self.ui.information("Passed Tests: " + str(passed_tests))
                self.ui.new_para()
            else:
                self.ui.information("No failed tests.", True)
                self.ui.information("Passed Tests: " + str(passed_tests))
                self.ui.new_para()
            if failed_tests > 0:
                self.ui.instruction("View failure reports in context in the above output.")
                if self.is_fast_fail:
                    sys.exit(str(failed_tests) + " test failures. " + str(passed_tests) + " test passes.")
            else:
                sys.exit(0)

        next_steps = []
        for line in classified_lines:
            if line["type"] == "next_step" and len(line["text"].strip()) > 0:
                next_steps.append(line)

        if len(next_steps) > 0:
            if self.is_prerequisite:
                return
            in_string = ""
            in_value = 0
            self.ui.instruction("Would you like to move on to one of the next steps listed above?")

            while in_value < 1 or in_value > len(next_steps):
                self.ui.instruction("Enter a value between 1 and " + str(len(next_steps)) + " or 'quit'")
                in_string = input()
                if in_string.lower() == "quit" or in_string.lower() == "q":
                    return
                try:
                    in_value = int(in_string)
                except ValueError:
                    pass

            pattern = re.compile('.*\[.*\]\((.*)\/(.*)\).*')
            match = pattern.match(next_steps[in_value - 1]["text"])
            self.script_dir = self.script_dir + match.groups()[0]
            self.filename = match.groups()[1]
            self.run()
            
    def classify_lines(self, lines):
        in_code_block = False
        in_results_section = False
        is_first_line = True
        in_next_steps = False
        in_prerequisites = False
        executed_code_in_this_section = False

        classified_lines = []

        for line in lines:
            if line.startswith("Results:"):
                # Entering results section
                in_results_section = True
            elif line.startswith("```") and not in_code_block:
                # Entering a code block,
                # if in_results_section = True then it's a results block
                in_code_block = True
                pos = line.lower().find("expected_similarity=")
                if pos >= 0:
                    pos = pos + len("expected_similarity=")
                    similarity = line[pos:]
                    expected_similarity = float(similarity)
                else:
                    expected_similarity = 0.66
            elif line.startswith("```") and in_code_block and in_results_section:
                # Finishing results section
                in_results_section = False
                in_code_block = False
            elif line.startswith("```") and in_code_block:
                # Finishing code block
                in_code_block = False
                in_results_section = False
            elif in_results_section and in_code_block:
                classified_lines.append({"type": "result",
                                         "expected_similarity": expected_similarity,
                                         "text": line})
            elif in_code_block and not in_results_section:
                # Executable line
                if line.startswith("#"):
                    # comment
                    pass
                else:
                    classified_lines.append({"type": "executable",
                                             "text": line})
            elif line.startswith("#") and not in_code_block and not in_results_section and not self.is_automated:
                # Heading in descriptive text, indicating a new section
                if line.lower().strip().endswith("# next steps"):
                    in_next_steps = True
                elif line.lower().strip().endswith("# prerequisites"):
                    in_prerequisites = True
                else:
                    in_prerequisites = False
                    in_next_steps = False
                classified_lines.append({"type": "heading",
                                         "text": line})
            else:
                if in_next_steps:
                    classified_lines.append({"type": "next_step",
                                             "text": line})
                elif in_prerequisites:
                    classified_lines.append({"type": "prerequisite",
                                             "text": line})
                else:
                    classified_lines.append({"type": "description",
                                             "text": line})

            is_first_line = False

        return classified_lines

    def execute(self, lines):
        in_results = False
        expected_results = ""
        actual_results = ""
        failed_tests = 0
        passed_tests = 0
        in_prerequisites = False
        executed_code_in_this_section = False
        next_steps = []

        self.ui.clear(self)
        self.ui.prompt()
        for line in lines:
            if line["type"] == "result":
                in_results = True
                expected_results += line["text"]
                expected_similarity = line["expected_similarity"]
            elif line["type"] != "result" and in_results:
                # Finishing results section
                if self.is_testing:
                    ansi_escape = re.compile(r'\x1b[^m]*m')
                    if self.ui.test_results(expected_results, ansi_escape.sub('', actual_results), expected_similarity):
                        passed_tests += 1
                    else:
                        failed_tests += 1
                        if (self.is_fast_fail):
                            break
                expected_results = ""
                actual_results = ""
                in_results = False
            elif line["type"] == "prerequisite":
                in_prerequisites = True
            elif line["type"] != "prerequisites" and in_prerequisites:
                self.check_prerequisites(lines)
                in_prerequisites = False
                self.ui.heading(line["text"])
            elif line["type"] == "executable":
                if not self.is_learning:
                    self.ui.prompt()
                    self.ui.check_for_interactive_command(self)
                self.current_command = line["text"]
                actual_results = self.ui.simulate_command(self)
                executed_code_in_this_section = True
            elif line["type"] == "heading":
                self.ui.check_for_interactive_command(self)
                if not self.is_simulation:
                    self.ui.clear(self)
                    self.ui.heading(line["text"])
            else:
                if not self.is_simulation and line["type"] == "description":
                    # Descriptive text
                    self.ui.description(line["text"])
                if line["type"] == "next_step":
                    pattern = re.compile('(.*)\[(.*)\]\(.*\).*')
                    match = pattern.match(line["text"])
                    if match:
                        self.ui.next_step(match.groups()[0], match.groups()[1])
                   
            is_first_line = False

        return failed_tests, passed_tests
    
    def check_prerequisites(self, lines):
        """Check that all prerequisites have been run
        satisfied. If running in test mode assume that this is the
        case (pre-requisites should be handled in the test_plan"""
        if self.is_testing or self.is_automated:
            return

# FIXME: run validation steps here

        steps = []
        for line in lines:
            step = {}
            if line["type"] == "prerequisite" and len(line["text"].strip()) > 0:
                self.ui.description(line["text"])
                pattern = re.compile('.*\[(.*)\]\((.*)\).*')
                match = pattern.match(line["text"])
                if match:
                    step["title"] = match.groups()[0].strip()
                    href = match.groups()[1]
                    if not href.endswith(".md"):
                        if not href.endswith("/"):
                            href = href + "/"
                        href = href + "script.md"
                    step["href"] = href
                    steps.append(step)

        for step in steps:
            self.ui.new_para()
            self.ui.instruction("Have you satisfied the '" + step["title"] + "' prerequisite? (y/N)")
            
            selection = None
            while not selection:
                in_string = input()
                if in_string.lower() == "y" or in_string.lower() == "yes":
                    selection = "yes"
                elif in_string == "" or in_string.lower() =="n" or in_string.lower() == "no":
                    selection = "no"

            if selection == "no":
                path, filename = os.path.split(step["href"])
                if (step["href"].startswith(".")):
                    new_dir = self.script_dir + path
                else:
                    new_dir = path
                    
                self.ui.horizontal_rule()
                demo = Demo(self.ui, self.is_docker, new_dir, filename, self.is_simulation, self.is_automated, self.is_testing, self.is_fast_fail, self.is_learning, True);
                demo.run()
                self.ui.clear(self)
                self.ui.information("'" + step["title"] + "' prerequisite completed.", True)
                self.ui.new_para
                
                
