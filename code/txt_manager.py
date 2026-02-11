import os

def create_aniloader_txt(file_path):
    if not os.path.exists(file_path):
        with open(file_path, 'w', encoding='utf-8'):
            pass


def read_aniloader_txt(file_path):
    create_aniloader_txt(file_path)

    with open(file_path, 'r', encoding='utf-8') as file:
        lines = [line.rstrip('\n') for line in file]

    clear_aniloader_txt(file_path)
    return lines


def write_to_aniloader_txt_bak(file_path, lines):
    create_aniloader_txt(file_path)

    existing_lines = set()
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as file:
            for line in file:
                existing_lines.add(line.rstrip('\n'))


    new_lines = [line for line in lines if line not in existing_lines]
    all_lines = list(existing_lines) + new_lines

    with open(file_path, 'w', encoding='utf-8') as file:
        for line in all_lines:
            file.write(f"{line}\n")


def clear_aniloader_txt(file_path):
    open(file_path, 'w', encoding='utf-8').close()