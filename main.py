from urllib.request import urlopen
import urllib.error

from time import sleep
from datetime import datetime
from pathlib import Path

import json
import pickle
import hashlib
import urllib
import csv


# MARK: - Data -

needs_restart = True
sections_to_save = []
viewed_sections = set()

Path("./cache").mkdir(parents=True, exist_ok=True)


def pickle_path_for_url(url):
    return "./cache/" + str(int(hashlib.sha1(url.encode('utf-8')).hexdigest(), 16))


def json_data(url):
    global needs_restart

    url_path = pickle_path_for_url(url)

    try:
        return pickle.load(open(url_path, "rb"))
    except:
        pass

    try:
        response = urlopen(url, timeout=1)
        data = response.read().decode("utf-8")
        result = json.loads(data)[:-1]
        pickle.dump(result, open(url_path, "wb"))
        return result
    except urllib.error.URLError as e:
        print(e)
        needs_restart = True
        return []
    except Exception as e:
        if "timeout" in str(type(e).__name__):
            needs_restart = True
        else:
            print(e)
        return []


# MARK: - Fetching -


def fetch_schools():
    return json_data("https://www.northwestern.edu/class-descriptions/4780/index-v2.json")


def fetch_subjects_for_school(school_id):
    return json_data("https://www.northwestern.edu/class-descriptions/4780/{}/index-v2.json".format(school_id))


def fetch_info_for_path(path):
    return json_data("https://www.northwestern.edu{}/index-v2.json".format(path))


def fetch_section_info_for_path(path):
    return json_data("https://www.northwestern.edu{}-v2.json".format(path))


# MARK: - Processing -


def _process_school(school):
    if "id" not in school:
        return

    print(school["name"])

    school_id = school['id']
    subjects = fetch_subjects_for_school(school_id)
    subjects = sorted(subjects, key=lambda i: i['name'])
    for subject in subjects:
        _process_subject(subject, {'school': school['id']})


def _process_subject(subject, data):
    if 'name' not in subject:
        return

    subject_name = subject['name']
    data['subject'] = subject_name

    print('    ' + subject_name)
    classes = fetch_info_for_path(subject['path'])
    classes = sorted(classes, key=lambda i: i['name'])
    for class_item in classes:
        _process_class(class_item, data)


def _process_class(class_item, data):
    if 'name' not in class_item:
        return

    data['class'] = class_item['name']
    sections = fetch_info_for_path(class_item['path'])
    for section in sections:
        _process_section(section, data)


def _process_section(section, data):
    global sections_to_save, viewed_sections

    if 'path' not in section:
        return

    path = section['path']
    if path in viewed_sections:
        return

    cleaned = data.copy()
    section_info = fetch_section_info_for_path(path)
    viewed_sections.add(path)

    if len(section_info) == 1:
        section_info = section_info[0]

    if 'title' in section_info:
        cleaned['title'] = section_info['title'].replace(data['school'] + ' ', '')
    if 'topic' in section_info:
        cleaned['topic'] = section_info['topic']
    if 'class_mtg_info' in section_info:
        mtg_info = section_info['class_mtg_info'][0]
        if 'meet_t' in mtg_info:
            meet_t = mtg_info['meet_t']
            cleaned['time'] = meet_t
            if 'TBA' != meet_t:
                cleaned['custom_days_per_week'] = _days_per_week(meet_t)
                cleaned['custom_minutes_per_week'] = _minutes_per_week(meet_t)
        if 'meet_l' in mtg_info:
            cleaned['location'] = mtg_info['meet_l']
    if 'descriptions' in section_info:
        cleaned.update(cleaned_descriptions_for_descriptions(section_info['descriptions']))
    if 'instructors' in section_info:
        cleaned['instructors'] = [d['instructor_name'] for d in section_info['instructors']]
    if 'enrl_requirement' in section_info:
        cleaned['requirements'] = cleaned_requirements_for_requirements(section_info['enrl_requirement'])
    if 'class_attributes' in section_info:
        cleaned['attributes'] = section_info['class_attributes']

    sections_to_save.append(cleaned)


def _days_per_week(meeting_time):
    return meeting_time.count("Mo") + meeting_time.count("Tu") + meeting_time.count("We") + meeting_time.count("Th") + meeting_time.count("Fr") + meeting_time.count("Sa") + meeting_time.count("Su")


def _minutes_per_week(meeting_time):
    days = _days_per_week(meeting_time)
    time_range = meeting_time.split(' ', 1)[1]
    times = time_range.split(' - ')
    delta = datetime.strptime(times[1], '%I:%M%p') - datetime.strptime(times[0], '%I:%M%p')
    return int(delta.seconds / 60 * days)


def cleaned_descriptions_for_descriptions(descriptions):
    cleaned = {}
    for description in descriptions:
        name = description['name'].lower()
        value = description['value']
        if name == 'overview of class':
            cleaned['description_overview'] = value
        elif name == 'class materials (required)':
            cleaned['description_materials_required'] = value
        elif name == 'class materials (suggested)':
            cleaned['description_materials_suggested'] = value
        elif name == 'learning objectives':
            cleaned['description_objectives'] = value
        elif name == 'teaching method':
            cleaned['description_teaching_method'] = value
        elif name == 'evaluation method':
            cleaned['description_evaluation_method'] = ";".join(value.split('<br/>'))
        elif name == 'registration requirements':
            cleaned['description_registration_requirements'] = value
        elif name == 'class notes':
            cleaned['description_notes'] = value
    return cleaned


def cleaned_requirements_for_requirements(requirements):
    cleaned = []
    split = requirements.split('<br/>')
    for requirement in split:
        if requirement == 'Enrollment Requirements: Reserved for Freshmen and Sophomores':
            cleaned.append('Freshmen;Sophmores')
        elif requirement == 'Add Consent: Instructor Consent Required':
            cleaned.append('AddInstructorConsent')
        elif requirement == 'Drop Consent: Instructor Consent Required':
            cleaned.append('DropInstructorConsent')
        elif requirement == 'Enrollment Requirements: Registration is reserved for Music Majors Only':
            cleaned.append('MajorMusic')
        elif requirement == 'Enrollment Requirements: Registration is reserved for Music Majors/Minors.  Non-music students should register for the corresponding GEN_MUS course under the same catalog number.  Specific questions should be directed to the Music department.':
            cleaned.append('MajorMusic')
        elif requirement == 'Add Consent: Department Consent Required':
            cleaned.append('AddDepartmentConsent')
        elif requirement == 'Drop Consent: Department Consent Required':
            cleaned.append('DropDepartmentConsent')
        elif requirement == 'Enrollment Requirements: Restricted to Music Undergrads/Grads':
            cleaned.append('MajorMusic')
        elif requirement == 'Enrollment Requirements: Reserved for Master of Music Students':
            cleaned.append('MajorMasterMusic')
        elif requirement == 'Enrollment Requirements: Enrollment only open to MSL degree candidates.':
            cleaned.append('MajorMSL')
        elif requirement == 'Enrollment Requirements: MSL Students are not eligible to enroll':
            cleaned.append('MajorNotMSL')
        elif requirement == 'Enrollment Requirements: Business Associations or Corporations is a pre-requisite for this course.':
            cleaned.append('ClassRequirement')
        elif requirement == 'Enrollment Requirements: Registration is restricted to BME Students Only.':
            cleaned.append('MajorBME')
        elif requirement == 'Enrollment Requirements: Basic Tax OR LLM Tax':
            cleaned.append('ClassRequirement')
        elif requirement == 'Enrollment Requirements: Pre-Registration is reserved for CS and CE majors only.':
            cleaned.append('MajorMusic')
        elif ' must have taken ' in requirement or ' must have completed ' in requirement or 'prerequisite' in requirement.lower() or 'pre-req' in requirement.lower():
            cleaned.append('ClassRequirement')
        elif 'reserved for Music Majors Only' in requirement:
            cleaned.append('MajorMusic')
        elif 'Reserved for Medill' in requirement:
            cleaned.append('SchoolMedill')
        elif requirement == 'Enrollment Requirements: This section is currently closed to registration.  Please contact the department directly with any questions.':
            cleaned.append('ClosedToRegistration')
        elif 'for radio/tv/film major' in requirement.lower():
            cleaned.append('MajorRTVF')
        elif 'reserved for' in requirement.lower() or 'restricted ' in requirement.lower():
            cleaned.append('MajorOther')
        elif 'shopping cart' in requirement or 'must also register' in requirement:
            cleaned.append('DualEnrollment')
        elif requirement == 'Enrollment Requirements: ISP Majors':
            cleaned.append('MajorISP')
        elif 'pre-registration' in requirement.lower() or 'preregistration' in requirement.lower():
            pass
        elif requirement != '':
            cleaned.append('Other')
    return cleaned


while needs_restart:
    print("restarting")
    needs_restart = False
    sections_to_save = []
    viewed_sections = set()
    schools = fetch_schools()
    schools = sorted(schools, key=lambda i: i['name'])
    for school in schools:
        _process_school(school)


all_keys = set().union(*(d.keys() for d in sections_to_save))
keys = ['school', 'title', 'topic', 'time', 'custom_minutes_per_week', 'location', 'requirements', 'description_evaluation_method', 'description_overview']
print('unused keys: ' + str(all_keys.difference(keys)))

with open('./results.csv', 'w') as output_file:
    dict_writer = csv.DictWriter(output_file, keys, extrasaction='ignore')
    dict_writer.writeheader()
    dict_writer.writerows(sections_to_save)

print("done")
