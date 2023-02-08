"""Module save_files to handle file I/O for data in txt and parquet format

   This module relies on classes in mimocorb.buffer_control
"""

from mimocorb.buffer_control import BufferToTxtfile, BufferToParquetfile

# def save_to_txt(source_dict):
def save_to_txt(source_list=None, sink_list=None, observe_list=None, config_dict=None, **rb_info):
    sv = BufferToTxtfile(source_list, observe_list, config_dict,  **rb_info)
    sv()


def save_parquet(source_list=None, sink_list=None, observe_list=None, config_dict=None, **rb_info):
    sv = BufferToParquetfile(source_list, observe_list, config_dict,  **rb_info)
    sv()


if __name__ == "__main__":
    print("Script: " + os.path.basename(sys.argv[0]))
    print("Python: ", sys.version, "\n".ljust(22, '-'))
    print("THIS IS A MODULE AND NOT MEANT FOR STANDALONE EXECUTION")
