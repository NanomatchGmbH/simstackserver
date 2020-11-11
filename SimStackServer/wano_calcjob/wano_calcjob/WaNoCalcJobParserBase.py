from aiida.common import NotExistent
from aiida.orm import SinglefileData
from aiida.parsers import Parser

#from wano_calcjob.WaNoCalcJobBase import WaNoCalcJob


class WaNoCalcJobParser(Parser):
    _calcJobClass = None
    def __init__(self, node):
        """
        Initialize Parser instance
        Checks that the ProcessNode being passed was produced by a WaNoCalcJobParser.
        :param node: ProcessNode of calculation
        :param type node: :class:`aiida.orm.ProcessNode`
        """
        from aiida.common import exceptions
        super(WaNoCalcJobParser, self).__init__(node)
        #if not issubclass(node.process_class, WaNoCalcJobParser):
        #    raise exceptions.ParsingError("Can only parse WaNoCalcJobParser")

    def parse(self, **kwargs):
        try:
            retrieved_folder = self.retrieved
        except NotExistent as _:
            return self.exit(self.exit_codes.ERROR_MISSING_OUTPUT_FILES)

        #print("Printing folder contents")
        
        #for file in retrieved_folder.list_object_names():
        #    print(file)
        #print("End of print")
        #print(join(retrieved_folder, "output_dict.yml"))
        #print(join(retrieved_folder, "output_config.ini"))
        #vardict = ReportRenderer.render_everything(retrieved_folder)


        # Linearize those here, i.e. use ReportRenderer to parse them, then export using out

        mycls = self._calcJobClass
        for myfile in self._calcJobClass.output_files():
            try:
                with self.retrieved.open(myfile, 'rb') as opened_file:
                    output_node = SinglefileData(file=opened_file)
                    self.out(mycls.clean_path(mycls.dot_to_none(myfile)), output_node)
            except NotExistent as _:
                print("Could not find file %s"%myfile)
                return self.exit(self.exit_codes.ERROR_MISSING_OUTPUT_FILES)
        return self.exit_codes.EXIT_NORMAL
        """
            def out_many(self, out_dict):
        Attach outputs to multiple output ports.

        Keys of the dictionary will be used as output port names, values as outputs.

        :param out_dict: output dictionary
        :type out_dict: dict

        for key, value in out_dict.items():
            self.out(key, value)
        """

        #for filename in sorted(self.retrieved.list_object_names(dynmat_folder), key=natural_sort):
        #    pass
        #filename_stdout = self.node.get_option('output_filename')  # or get_attribute(), but this is clearer
