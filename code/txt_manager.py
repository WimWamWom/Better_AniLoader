
def read_txt_into_array(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        lines = [line.rstrip('\n') for line in file]
    return lines

def write_array_to_txt(file_path, lines):
    with open(file_path, 'w', encoding='utf-8') as file:
        for line in lines:
            file.write(f"{line}\n")

def clear_txt_file(file_path):
    open(file_path, 'w', encoding='utf-8').close()