from glob import glob
import os
import configparser
import pandas as pd
import numpy as np

lib_dir = './lib' # Can replace with ENV variable

def get_config_object():
    cfg = configparser.ConfigParser()
    cfg.read(f'{lib_dir}/tapi.ini')
    return cfg

def get_config(key, heading='DEFAULT'):
    cfg = get_config_object()
    return cfg[heading][key]

def list_prefixes(dir='corpora'):
    prefixes = []
    for filename in glob(f"./{dir}/*.csv"):
    # for filename in os.listdir(f"./{dir}/*.csv"):
        prefix = filename.split('-')[0]
        prefix = prefix.replace(f"./{dir}/", "")
        prefixes.append(prefix)
    return sorted(list(set(prefixes)))

def list_corpora():
    mydir = get_config('corpora_dir')
    return list_prefixes(mydir)

def list_dbs():
    mydir = get_config('db_dir')
    return list_prefixes(mydir)

def reduce_corpora(corpora, sample_size = 10000):
    """Legacy function; to be removed."""
    for corpus in corpora:
        prefix = corpus.split('/')[1].split('-')[0]
        if prefix == 'novels':
            sep = ','
        else:
            sep = '|'
        df = pd.read_csv(corpus, sep=sep, error_bad_lines=False, header=0)
        if df.shape[0] > sample_size:
            df = df.sample(sample_size).copy()
            
        df.to_csv(f"corpora/{prefix}-tapi.csv", sep='|', index=False)

def constellate_to_corpus(in_jsonl_file, out_csv_file):
    """Legacy function. To be refactored."""

    # Example files:
    # in_file = './corpora/4c5cb65a-f26b-d753-a419-ca63e1df90f3-sampled-jsonl'
    # out_file = 'corpora/jstor_hyperparameter-corpus.csv'

    coll = pd.DataFrame(open(in_jsonl_file, 'r').readlines())
    coll.columns = ['raw']

    def get_element(doc, key):
        rec = json.loads(doc)
        val = None
        try:
            val = rec[key]
        except:
            pass
        return val

    coll['doc_content'] = coll.raw.apply(lambda x: get_element(x, 'abstract')).dropna()
    coll['doc_title'] = coll.raw.apply(lambda x: get_element(x, 'title'))
    coll['doc_url'] = coll.raw.apply(lambda x: get_element(x, 'id'))
    coll['doc_key'] = coll.doc_url.str.replace(r'http://www.jstor.org/stable/', '', regex=False)
    coll['doc_date'] = coll.raw.apply(lambda x: get_element(x, 'datePublished'))
    coll['doc_year'] = coll.doc_date.apply(lambda x: int(x.split('-')[0]))
    coll['doc_lang'] = coll.raw.apply(lambda x: get_element(x, 'language'))
    coll['doc_tdmcat'] = coll.raw.apply(lambda x: get_element(x, 'tdmCategory'))
    coll['doc_srccat'] = coll.raw.apply(lambda x: get_element(x, 'sourceCategory'))

    coll = coll[~coll.doc_content.isna()]    
    
    coll.iloc[:,1:].to_csv(out_csv_file, sep='|', index=False)


class Edition:
    """An Edition is a collection of analytical tables derived from a corpus."""   

    # These tables compose a schema, or data model, of a digital analytical edition
    tables = dict(
        LABELS = dict(id='doc_id'), 
        VOCAB = dict(id='term_str'), 
        BOW = dict(id=['doc_id','term_str']), 
        TOPICS = dict(id='topic_id'), 
        DTM = dict(id='doc_id'), 
        THETA = dict(id='doc_id'), 
        PHI = dict(id='topic_id'), 
        TOPICS_NMF = dict(id='topic_id'), 
        THETA_NMF = dict(id='doc_id'), 
        PHI_NMF = dict(id='topic_id')
    )

    def __init__(self, data_prefix='default'):
        self.data_prefix = data_prefix
        for table in self.tables.keys():
            setattr(self, table, pd.DataFrame())        

    def get_corpus(self, csv_sep=None):
        cfg = get_config_object()
        corpora_dir = cfg['DEFAULT']['corpora_dir']
        if not csv_sep:
            csv_sep = cfg['DEFAULT']['corpora_csv_sep']
        corpus_file = f'{corpora_dir}/{self.data_prefix}-tapi.csv'
        try:
            corpus = pd.read_csv(corpus_file, sep=csv_sep)
            corpus.index.name = 'doc_id'
            return corpus
        except FileNotFoundError as e:
            print(f"Corpus file {corpus_file} not found.")
            return False

    def save_tables(self):
        db_dir = get_config('db_dir')
        for table in self.tables.keys():
            getattr(self, table).to_csv(f"{db_dir}/{self.data_prefix}-{table}.csv", 
            index=True)    

    def get_tables(self):
        db_dir = get_config('db_dir')  
        for table in self.tables.keys():
            try:
                setattr(self, table, pd.read_csv(f"{db_dir}/{self.data_prefix}-{table}.csv")\
                    .set_index(self.tables[table]['id'])) 
                print(table)
            except FileNotFoundError as e:
                print(table + ' not found')

        # Improve this  
        self.THETA.columns.name = 'topic_id'
        self.THETA.columns = [int(col) for col in self.THETA.columns] # Should change columns to strings
        self.PHI.columns.name = 'term_str'
        self.THETA_NMF.columns.name = 'topic_id'
        self.THETA_NMF.columns = [int(col) for col in self.THETA_NMF.columns] # Should change columns to strings
        self.PHI_NMF.columns.name = 'term_str'

        self.n_topics = len(self.TOPICS)
        self.topic_cols = [t for t in range(self.n_topics)]

    def get_table(self, table):
        db_dir = get_config('db_dir')

        try:
            _ = self.tables[table]
        except KeyError:
            print(table + ' not in schema')
            
        try:
            setattr(self, table, pd.read_csv(f"{db_dir}/{self.data_prefix}-{table}.csv")\
                .set_index(self.tables[table]['id'])) 
            print(table)
        except FileNotFoundError as e:
            print(table + ' not found')
        
        if 'THETA' in table:
            obj = getattr(self, table)
            obj.columns.name = 'topic_id'
            obj.columns = [int(col) for col in self.THETA.columns] # Should change columns to strings
        if 'PHI' in table:
            obj = getattr(self, table)
            obj.columns.name = 'term_str'

    def get_labels(self):
        labels = []
        for label in self.LABELS.columns.to_list():
            nvals = len(self.LABELS[label].value_counts())
            labels.append((label, nvals))
        df = pd.DataFrame(labels)
        df.columns = ['label_name', 'n']
        df = df.set_index('label_name')
        return df

if __name__ == '__main__':

    list_corpora()
